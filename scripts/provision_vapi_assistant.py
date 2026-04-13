#!/usr/bin/env python3
"""Provision Vapi Assistant for Henry PM (voice interface).

Creates a Vapi voice assistant for Henry PM and stores the VAPI_ASSISTANT_ID
in .env for later use.

Env vars:
    VAPI_API_KEY      — Vapi API key
    VAPI_ASSISTANT_ID — Output: will be set in .env after provisioning
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def provision_vapi_assistant(business_name: str = "Hermes") -> dict:
    """Create a Vapi voice assistant for Henry PM.

    Parameters
    ----------
    business_name : str
        Name of the business (used in assistant description).

    Returns
    -------
    dict
        Result with keys:
        - assistant_id: str
        - phone_number: str (if available)
        - status: str
        - message: str
    """
    api_key = os.getenv("VAPI_API_KEY")
    if not api_key:
        logger.error("VAPI_API_KEY not set. Cannot provision Vapi assistant.")
        return {
            "status": "error",
            "message": "VAPI_API_KEY not set",
            "assistant_id": None,
        }

    try:
        # Try to use vapi SDK or direct HTTP calls
        import httpx

        logger.info(f"Provisioning Vapi assistant for {business_name}...")

        # Create assistant via Vapi API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.vapi.ai/assistants",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "name": f"Henry PM - {business_name}",
                    "model": {
                        "provider": "openai",
                        "model": "gpt-4",
                        "systemPrompt": (
                            f"You are Henry, the AI Project Manager for {business_name}. "
                            "You manage a team of AI agents and report to the business owner. "
                            "Be professional, clear, and concise in voice calls."
                        ),
                    },
                    "voice": {
                        "provider": "openai",
                        "voiceId": "nova",  # OpenAI voice
                    },
                },
                timeout=30,
            )

            if response.status_code != 201:
                logger.error(f"Vapi API error: {response.text}")
                return {
                    "status": "error",
                    "message": f"Vapi API error: {response.status_code}",
                    "assistant_id": None,
                }

            result_data = response.json()
            assistant_id = result_data.get("id")
            phone_number = result_data.get("phoneNumber", "")

            logger.info(f"Created Vapi assistant: {assistant_id}")

            # Save to .env
            env_path = Path.home() / ".hermes" / ".env"
            env_path.parent.mkdir(parents=True, exist_ok=True)

            # Append or update VAPI_ASSISTANT_ID
            env_lines = []
            if env_path.exists():
                env_lines = env_path.read_text().strip().split("\n")

            # Filter out existing VAPI_ASSISTANT_ID line
            env_lines = [line for line in env_lines if not line.startswith("VAPI_ASSISTANT_ID=")]
            env_lines.append(f"VAPI_ASSISTANT_ID={assistant_id}")

            env_path.write_text("\n".join(env_lines) + "\n")
            logger.info(f"Saved VAPI_ASSISTANT_ID to {env_path}")

            return {
                "status": "success",
                "message": f"Provisioned Vapi assistant {assistant_id}",
                "assistant_id": assistant_id,
                "phone_number": phone_number,
            }

    except ImportError:
        logger.warning("httpx not available. Using fallback provisioning.")
        # Fallback: just create a placeholder
        assistant_id = f"vapi_{business_name.lower().replace(' ', '_')}"
        logger.info(f"Using placeholder Vapi assistant: {assistant_id}")
        return {
            "status": "pending",
            "message": "Vapi provisioning pending (httpx not available)",
            "assistant_id": assistant_id,
            "phone_number": None,
        }

    except Exception as exc:
        logger.error(f"Vapi provisioning failed: {exc}")
        return {
            "status": "error",
            "message": str(exc),
            "assistant_id": None,
        }


async def main():
    """Entry point for provisioning Vapi assistant."""
    if len(sys.argv) > 1:
        business_name = sys.argv[1]
    else:
        business_name = "Hermes"

    result = await provision_vapi_assistant(business_name)
    print(json.dumps(result, indent=2))

    if result["status"] == "success":
        print(f"\nVapi Assistant ID: {result['assistant_id']}")
        if result["phone_number"]:
            print(f"Phone Number: {result['phone_number']}")
        sys.exit(0)
    else:
        print(f"Error: {result['message']}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
