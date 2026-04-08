#!/usr/bin/env python3
"""
Google AI Image Generation Tool

Generates images using Google's Gemini API (gemini-2.0-flash-exp with image output).
Images are saved to disk so they can be uploaded via browser automation.

Requires: GEMINI_API_KEY environment variable.
Get one free at: https://aistudio.google.com/apikey
"""

import base64
import json
import logging
import os
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Where generated images are stored
IMAGES_DIR = Path(os.path.expanduser("~/.hermes/generated-images"))

# API config
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.0-flash-exp"

# Aspect ratio presets (width x height)
ASPECT_RATIOS = {
    "square": "1:1",
    "portrait": "9:16",
    "landscape": "16:9",
    "story": "9:16",       # Instagram story
    "post": "4:5",         # Instagram feed optimal
    "wide": "16:9",
}


def _ensure_images_dir() -> Path:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    return IMAGES_DIR


def _get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        # Try loading from ~/.hermes/.env
        env_file = Path(os.path.expanduser("~/.hermes/.env"))
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("GEMINI_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    return key


def google_image_generate(
    prompt: str,
    aspect_ratio: str = "square",
    style: Optional[str] = None,
) -> str:
    """Generate an image using Google Gemini and save it to disk.

    Args:
        prompt: Text description of the image to generate.
        aspect_ratio: One of square, portrait, landscape, story, post, wide.
        style: Optional style modifier (e.g. "photorealistic", "illustration",
               "watercolor"). Appended to the prompt.

    Returns:
        JSON string with success status and file_path of saved image.
    """
    api_key = _get_api_key()
    if not api_key:
        return json.dumps({
            "success": False,
            "error": "GEMINI_API_KEY not set. Get one free at https://aistudio.google.com/apikey",
            "file_path": None,
        })

    # Build the full prompt
    full_prompt = prompt.strip()
    if style:
        full_prompt = f"{full_prompt}, {style} style"

    # Add aspect ratio hint to prompt
    ar = ASPECT_RATIOS.get(aspect_ratio, aspect_ratio)

    # Build request body
    body = {
        "contents": [
            {
                "parts": [
                    {"text": full_prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
        },
    }

    url = f"{GEMINI_API_URL}/{DEFAULT_MODEL}:generateContent?key={api_key}"

    try:
        logger.info("Generating image with Gemini: %s", full_prompt[:80])
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())

        # Extract image from response
        candidates = result.get("candidates", [])
        if not candidates:
            return json.dumps({
                "success": False,
                "error": "No candidates in Gemini response",
                "file_path": None,
            })

        parts = candidates[0].get("content", {}).get("parts", [])
        image_data = None
        mime_type = "image/png"
        caption_text = ""

        for part in parts:
            if "inlineData" in part:
                image_data = part["inlineData"]["data"]
                mime_type = part["inlineData"].get("mimeType", "image/png")
            elif "inline_data" in part:
                image_data = part["inline_data"]["data"]
                mime_type = part["inline_data"].get("mimeType", "image/png")
            elif "text" in part:
                caption_text = part["text"]

        if not image_data:
            return json.dumps({
                "success": False,
                "error": "No image data in Gemini response. The model may have refused the prompt.",
                "file_path": None,
            })

        # Save to disk
        ext = "png" if "png" in mime_type else "jpg"
        _ensure_images_dir()
        timestamp = int(time.time())
        # Clean filename from prompt
        safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in prompt[:40]).strip().replace(" ", "_")
        filename = f"gemini_{safe_name}_{timestamp}.{ext}"
        file_path = IMAGES_DIR / filename

        with open(file_path, "wb") as f:
            f.write(base64.b64decode(image_data))

        file_size = file_path.stat().st_size
        logger.info("Image saved: %s (%d bytes)", file_path, file_size)

        return json.dumps({
            "success": True,
            "file_path": str(file_path),
            "filename": filename,
            "size_bytes": file_size,
            "mime_type": mime_type,
            "caption": caption_text,
        })

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error("Gemini API error %d: %s", e.code, error_body[:500])
        return json.dumps({
            "success": False,
            "error": f"Gemini API error {e.code}: {error_body[:200]}",
            "file_path": None,
        })
    except Exception as e:
        logger.error("Image generation failed: %s", e, exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "file_path": None,
        })


def check_google_image_requirements() -> bool:
    return bool(_get_api_key())


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
from tools.registry import registry

GOOGLE_IMAGE_SCHEMA = {
    "name": "google_image_generate",
    "description": (
        "Generate images using Google Gemini AI. Creates high-quality images from text prompts "
        "and saves them to disk. Returns the file path of the saved image. "
        "Use this to create images for Instagram posts, social media content, marketing materials, etc. "
        "The saved image can then be uploaded to Instagram or other platforms using browser_upload_file."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Detailed description of the image to generate. Be specific about subject, style, lighting, composition.",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["square", "portrait", "landscape", "story", "post", "wide"],
                "description": "Image aspect ratio. 'post' (4:5) is optimal for Instagram feed. 'story' (9:16) for Instagram stories. 'square' (1:1) works everywhere.",
                "default": "square",
            },
            "style": {
                "type": "string",
                "description": "Optional style modifier like 'photorealistic', 'illustration', 'watercolor', 'cinematic', '3D render'. Appended to prompt.",
            },
        },
        "required": ["prompt"],
    },
}

registry.register(
    name="google_image_generate",
    toolset="image_gen",
    schema=GOOGLE_IMAGE_SCHEMA,
    handler=lambda args, **kw: google_image_generate(
        prompt=args.get("prompt", ""),
        aspect_ratio=args.get("aspect_ratio", "square"),
        style=args.get("style"),
    ),
    check_fn=check_google_image_requirements,
    requires_env=["GEMINI_API_KEY"],
    is_async=False,
    emoji="🎨",
)
