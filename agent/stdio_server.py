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
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class StdioServerError(Exception):
    pass


class StdioServer:
    """
    Handles JSON-L messages from stdin and writes JSON-L responses to stdout.

    dry_run=True skips actual LLM calls — used in tests.
    """

    def __init__(self, session_id: Optional[str] = None, dry_run: bool = False):
        self.session_id = session_id
        self.dry_run = dry_run
        self._agent = None  # lazy-init real AIAgent when not dry_run

    async def handle_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process one message, return final response dict."""
        session_id = payload.get("session_id", "").strip()
        message = payload.get("message", "").strip()

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

        # Real agent execution
        agent = await self._get_agent()
        content = await agent.run(message)
        return {
            "session_id": session_id,
            "done": True,
            "content": content,
            "usage": {},
        }

    async def _get_agent(self):
        if self._agent is None:
            # Import here to avoid slow startup in dry_run / test mode
            from run_agent import create_agent
            self._agent = await create_agent(session_id=self.session_id)
        return self._agent

    async def run_forever(self) -> None:
        """Main loop: read JSON-L from stdin, write JSON-L to stdout."""
        loop = asyncio.get_event_loop()

        reader = asyncio.StreamReader()
        read_protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: read_protocol, sys.stdin)

        write_transport, write_protocol = await loop.connect_write_pipe(
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
