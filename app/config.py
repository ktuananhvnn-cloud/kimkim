"""Central place that reads all configuration from environment variables.

Secrets (API keys, tokens, DB credentials) live ONLY here / in .env on the
VPS. The admin website must never read process env vars into an HTTP
response - it only edits the non-secret rows in the `config` / `prompts`
Supabase tables (see app/db/supabase_client.py).
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


class Settings:
    # Empty on purpose when using a Claude subscription (see ANTHROPIC_CONFIG_DIR
    # in .env / README) instead of a metered API key - app/bot/agent.py falls
    # back to the SDK's own credential resolution (ANTHROPIC_AUTH_TOKEN, then an
    # `ant auth login` OAuth profile) when this is blank.
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    claude_model: str = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")

    telegram_bot_token: str = _require("TELEGRAM_BOT_TOKEN")
    telegram_owner_id: int = int(_require("TELEGRAM_OWNER_ID"))

    supabase_url: str = _require("SUPABASE_URL")
    supabase_service_key: str = _require("SUPABASE_SERVICE_KEY")

    admin_username: str = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password_hash: str = os.environ.get("ADMIN_PASSWORD_HASH", "")
    admin_session_secret: str = os.environ.get(
        "ADMIN_SESSION_SECRET", "dev-only-insecure-secret"
    )
    admin_port: int = int(os.environ.get("ADMIN_PORT", "8080"))

    market_data_source: str = os.environ.get("MARKET_DATA_SOURCE", "vndirect")

    log_level: str = os.environ.get("LOG_LEVEL", "INFO")


settings = Settings()
