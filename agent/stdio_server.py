# agent/stdio_server.py
"""
StdioServer — runs the Hermes agent as a long-running JSON-L stdio process.

Protocol:
  stdin  (one JSON object per line):
    {"session_id": "x", "message": "hello", "platform": "telegram"}

  stdout (one JSON object per line):
    {"session_id": "x", "done": true, "content": "Hello!", "usage": {}}

  stderr: debug/error logs only (never parsed by gateway)

Usage:
  hermes agent serve --transport stdio [--session-id SESSION_ID]
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StdioServerError(Exception):
    pass


def _resolve_agent_kwargs() -> dict:
    """Resolve provider credentials — same logic as the gateway."""
    from hermes_cli.runtime_provider import resolve_runtime_provider
    runtime = resolve_runtime_provider()
    return {
        "api_key": runtime.get("api_key"),
        "base_url": runtime.get("base_url"),
        "provider": runtime.get("provider"),
        "api_mode": runtime.get("api_mode"),
        "command": runtime.get("command"),
        "args": list(runtime.get("args") or []),
        "credential_pool": runtime.get("credential_pool"),
    }


def _resolve_model() -> str:
    """Read model from config.yaml."""
    try:
        from hermes_constants import get_hermes_home
        import yaml
        cfg_path = get_hermes_home() / "config.yaml"
        if cfg_path.exists():
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            model_cfg = cfg.get("model", {})
            if isinstance(model_cfg, str):
                return model_cfg
            if isinstance(model_cfg, dict):
                return model_cfg.get("default") or model_cfg.get("model") or ""
    except Exception as e:
        logger.debug("Could not read model from config.yaml: %s", e)
    return ""


def _load_history(session_id: str) -> List[Dict[str, Any]]:
    """Load conversation history from the session transcript store.

    Iterates line-by-line to avoid loading the entire transcript into memory
    for long-running sessions.
    """
    try:
        from hermes_constants import get_hermes_home
        transcripts_dir = get_hermes_home() / "sessions"
        transcript_path = transcripts_dir / f"{session_id}.jsonl"
        if not transcript_path.exists():
            return []
        messages = []
        with open(transcript_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    role = msg.get("role")
                    if role in ("user", "assistant", "tool") and msg.get("content"):
                        messages.append({"role": role, "content": msg["content"]})
                except json.JSONDecodeError:
                    pass
        return messages
    except Exception as e:
        logger.debug("Could not load history for session %s: %s", session_id, e)
        return []


class StdioServer:
    """
    Handles JSON-L messages from stdin and writes JSON-L responses to stdout.

    Owns its own AIAgent instance per session — resolves credentials and loads
    history from the transcript store so it is fully self-contained.

    dry_run=True skips actual LLM calls — used in tests.
    """

    def __init__(self, session_id: Optional[str] = None, dry_run: bool = False):
        self.session_id = session_id
        self.dry_run = dry_run
        self._agent = None  # lazy-init on first real message

    async def handle_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process one message, return final response dict."""
        session_id = payload.get("session_id", "").strip()
        message = payload.get("message", "").strip()
        platform = payload.get("platform", "api")

        if not session_id:
            raise StdioServerError("session_id required")
        if not message:
            raise StdioServerError("message required")

        if self.dry_run:
            return {
                "session_id": session_id,
                "done": True,
                "content": f"[dry-run echo] {message}",
                "usage": {},
            }

        # Extract W3C traceparent from gateway so this span is a child of gateway.dispatch_subprocess
        traceparent = payload.get("traceparent")
        _otel_parent_ctx = None
        if traceparent:
            try:
                from opentelemetry.propagate import extract
                _otel_parent_ctx = extract({"traceparent": traceparent})
            except Exception:
                pass

        from agent.telemetry import get_tracer
        _tracer = get_tracer("hermes")
        with _tracer.start_as_current_span(
            "stdio_server.handle_message",
            context=_otel_parent_ctx,  # None → new root span (graceful fallback)
        ) as _span:
            try:
                _span.set_attribute("session_id", session_id)
                _span.set_attribute("platform", platform)
                _span.set_attribute("message_length", len(message))
            except Exception:
                pass
            agent = self._get_or_create_agent(session_id, platform)
            history = _load_history(session_id)

            import contextvars as _cv
            _stdio_ctx = _cv.copy_context()
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: _stdio_ctx.run(
                    agent.run_conversation,
                    message,
                    conversation_history=history,
                    task_id=session_id,
                ),
            )

            content = result.get("final_response") or result.get("error") or ""
            _span.set_attribute("response_length", len(content))
            _span.set_attribute(
                "input_tokens", getattr(agent, "session_prompt_tokens", 0)
            )
            _span.set_attribute(
                "output_tokens", getattr(agent, "session_completion_tokens", 0)
            )
            return {
                "session_id": session_id,
                "done": True,
                "content": content,
                "usage": {
                    "input_tokens": getattr(agent, "session_prompt_tokens", 0),
                    "output_tokens": getattr(agent, "session_completion_tokens", 0),
                },
            }

    def _get_or_create_agent(self, session_id: str, platform: str):
        """Return cached agent or create one for this session."""
        if self._agent is not None:
            return self._agent

        from run_agent import AIAgent
        from dotenv import load_dotenv
        from hermes_constants import get_hermes_home

        # Re-read credentials (long-lived process — keys may change)
        env_path = get_hermes_home() / ".env"
        try:
            load_dotenv(env_path, override=True, encoding="utf-8")
        except Exception as e:
            logger.debug("Could not load .env file %s: %s", env_path, e)

        model = _resolve_model()
        try:
            runtime_kwargs = _resolve_agent_kwargs()
        except Exception as e:
            raise StdioServerError(f"Provider auth failed: {e}") from e

        self._agent = AIAgent(
            model=model,
            **runtime_kwargs,
            max_iterations=90,
            quiet_mode=True,
            verbose_logging=False,
            session_id=session_id,
            platform=platform,
        )
        return self._agent

    async def run_forever(self) -> None:
        """Main loop: read JSON-L from stdin, write JSON-L to stdout."""
        # Initialise telemetry once at server start (non-fatal).
        try:
            from agent.telemetry import configure_from_config
            configure_from_config()
        except Exception as _tel_err:
            logger.debug("Telemetry init skipped: %s", _tel_err)

        loop = asyncio.get_event_loop()

        reader = asyncio.StreamReader()
        read_protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: read_protocol, sys.stdin)

        write_transport, _ = await loop.connect_write_pipe(
            asyncio.BaseProtocol, sys.stdout.buffer
        )

        logger.debug("StdioServer ready, waiting for input")

        while True:
            try:
                line = await reader.readline()
                if not line:
                    break  # EOF — gateway closed the pipe

                line_str = line.decode().strip()
                if not line_str:
                    continue

                try:
                    payload = json.loads(line_str)
                except json.JSONDecodeError as e:
                    err = json.dumps({"error": f"invalid JSON: {e}"}) + "\n"
                    write_transport.write(err.encode())
                    continue

                try:
                    response = await self.handle_message(payload)
                except StdioServerError as e:
                    response = {
                        "session_id": payload.get("session_id", ""),
                        "error": str(e),
                        "done": True,
                    }

                out = json.dumps(response) + "\n"
                write_transport.write(out.encode())

            except (BrokenPipeError, ConnectionResetError):
                break
            except Exception as e:
                logger.exception("Unhandled error in StdioServer loop: %s", e)


async def main(session_id: Optional[str] = None) -> None:
    server = StdioServer(session_id=session_id)
    await server.run_forever()
