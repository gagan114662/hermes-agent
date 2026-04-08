# agent/provider_router.py
"""
Multi-provider API routing for Hermes.

Supported providers: anthropic, openrouter, bedrock, azure, vertex.
Reads configuration from environment variables or ~/.hermes/.env.

Usage:
    from agent.provider_router import resolve_provider_config
    config = resolve_provider_config()
    # Returns: {"provider": "bedrock", "base_url": ..., "api_key": ..., "model": ...}
"""
import os
import logging

logger = logging.getLogger(__name__)

PROVIDER_CONFIGS = {
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
        "description": "Direct Anthropic API",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "description": "OpenRouter (multi-model proxy)",
    },
    "bedrock": {
        "base_url": None,  # Handled by boto3
        "api_key_env": None,  # Uses AWS credentials
        "description": "AWS Bedrock (enterprise)",
        "note": "Requires: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION",
    },
    "azure": {
        "base_url_template": "https://{resource}.openai.azure.com/openai/deployments/{deployment}",
        "api_key_env": "AZURE_OPENAI_API_KEY",
        "description": "Azure OpenAI Service",
        "note": "Requires: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT",
    },
    "vertex": {
        "base_url_template": "https://{region}-aiplatform.googleapis.com/v1/projects/{project}/locations/{region}/publishers/google/models/{model}:streamGenerateContent",
        "api_key_env": None,  # Uses Google ADC
        "description": "Google Cloud Vertex AI",
        "note": "Requires: GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_REGION",
    },
}


def resolve_provider_config(
    provider: str = None,
    model: str = None,
) -> dict:
    """Resolve provider configuration from environment.

    Provider detection order:
    1. Explicit provider argument
    2. HERMES_PROVIDER env var
    3. Infer from model name prefix (anthropic/, openai/, etc.)
    4. Default to openrouter

    Returns dict with: provider, base_url, api_key, model, description
    """
    # Load .env if exists
    env_file = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_file):
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        if key.strip() not in os.environ:
                            os.environ[key.strip()] = val.strip()
        except Exception:
            pass

    # Determine provider
    if provider is None:
        provider = os.environ.get("HERMES_PROVIDER", "").lower().strip()

    if not provider and model:
        # Infer from model name — check explicit prefixes first
        if model.startswith("bedrock/"):
            provider = "bedrock"
        elif model.startswith("azure/"):
            provider = "azure"
        elif model.startswith("vertex/"):
            provider = "vertex"
        elif model.startswith("anthropic/") or "claude" in model.lower():
            provider = "openrouter"  # Default Claude path

    if not provider:
        provider = "openrouter"

    config = PROVIDER_CONFIGS.get(provider, PROVIDER_CONFIGS["openrouter"]).copy()

    # Resolve API key
    api_key = None
    api_key_env = config.get("api_key_env")
    if api_key_env:
        api_key = os.environ.get(api_key_env) or os.environ.get("OPENROUTER_API_KEY")

    return {
        "provider": provider,
        "base_url": config.get("base_url"),
        "api_key": api_key,
        "model": model,
        "description": config.get("description", provider),
    }


def list_providers() -> list:
    """Return list of all supported providers with their descriptions."""
    return [
        {"provider": k, "description": v["description"], "notes": v.get("note", "")}
        for k, v in PROVIDER_CONFIGS.items()
    ]
