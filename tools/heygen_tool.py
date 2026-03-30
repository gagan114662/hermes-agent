"""
HeyGen Avatar Tool — generate talking-head videos using HeyGen API.

Env vars required:
    HEYGEN_API_KEY   — HeyGen API key
    HEYGEN_AVATAR_ID — Avatar ID for this AI employee
    HEYGEN_VOICE_ID  — Voice ID for this AI employee
"""
import logging
import os
import time
import httpx
from tools.registry import registry

logger = logging.getLogger(__name__)

HEYGEN_BASE = "https://api.heygen.com"


def _headers():
    return {
        "X-Api-Key": os.environ["HEYGEN_API_KEY"],
        "Content-Type": "application/json",
    }


def heygen_generate_video_tool(script: str, wait: bool = True) -> str:
    """Generate a talking-head video of the AI employee saying the given script."""
    payload = {
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": os.environ["HEYGEN_AVATAR_ID"],
                    "avatar_style": "normal",
                },
                "voice": {
                    "type": "text",
                    "input_text": script,
                    "voice_id": os.environ["HEYGEN_VOICE_ID"],
                },
            }
        ],
        "dimension": {"width": 1280, "height": 720},
    }
    try:
        resp = httpx.post(
            f"{HEYGEN_BASE}/v2/video/generate",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        video_id = data.get("data", {}).get("video_id")
        if not video_id:
            return f"Error: no video_id in response"

        if not wait:
            return f"Video generation started. Video ID: {video_id}"

        # Poll for completion (max 3 minutes)
        for _ in range(36):
            time.sleep(5)
            status_resp = httpx.get(
                f"{HEYGEN_BASE}/v1/video_status.get",
                headers=_headers(),
                params={"video_id": video_id},
                timeout=15,
            )
            status_resp.raise_for_status()
            sdata = status_resp.json().get("data", {})
            status = sdata.get("status")
            if status == "completed":
                return f"Video ready: {sdata.get('video_url', '')}"
            elif status == "failed":
                return f"Video generation failed: {sdata.get('error')}"

        return f"Video still processing. Video ID: {video_id}"

    except httpx.HTTPStatusError as e:
        logger.error("HeyGen error: %s", e.response.status_code)
        return f"Error: HTTP {e.response.status_code}"
    except httpx.TimeoutException:
        return "Error: HeyGen request timed out"
    except httpx.ConnectError:
        return "Error: Could not connect to HeyGen API"
    except Exception as e:
        logger.error("HeyGen unexpected error: %s", e)
        return "Error: unexpected error generating video"


def _check_heygen():
    if not os.getenv("HEYGEN_API_KEY"):
        return False, "HEYGEN_API_KEY not set"
    if not os.getenv("HEYGEN_AVATAR_ID"):
        return False, "HEYGEN_AVATAR_ID not set"
    if not os.getenv("HEYGEN_VOICE_ID"):
        return False, "HEYGEN_VOICE_ID not set"
    return True, "HeyGen configured"


registry.register(
    name="heygen_video",
    toolset="avatar",
    schema={
        "name": "heygen_video",
        "description": "Generate a talking-head video of the AI employee avatar saying a given script. Returns a video URL when complete.",
        "parameters": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "What the avatar should say in the video"},
                "wait": {"type": "boolean", "description": "Wait for completion and return video URL (default true). Set false to return immediately with video ID.", "default": True},
            },
            "required": ["script"],
        },
    },
    handler=lambda args, **kw: heygen_generate_video_tool(args["script"], args.get("wait", True)),
    check_fn=_check_heygen,
    requires_env=["HEYGEN_API_KEY", "HEYGEN_AVATAR_ID", "HEYGEN_VOICE_ID"],
    emoji="🎬",
)
