"""Configuration loading: settings.yaml + .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


@dataclass
class DailySnapshotConfig:
    fetch_limit: int = 20
    min_volume_24h_usd: float = 0
    top_tokens_count: int = 3
    hot_pairs_count: int = 3
    whale_flows_count: int = 3
    whale_min_volume_24h_usd: float = 1_000_000
    whale_exclude_base_tokens: list[str] = field(
        default_factory=lambda: ["USDC", "USDT", "SOL", "WSOL"]
    )
    display_aliases: dict[str, str] = field(default_factory=dict)
    label_max_chars: int = 40
    discord_color: int = 0x9945FF  # Solana purple
    enable_discord: bool = True
    enable_x: bool = True
    enable_jp_translation: bool = False  # token tickers are universal — off by default
    jp_translation_provider: str = "gemini"  # "gemini" | "anthropic"
    jp_translation_model: str = "gemini-2.5-flash-lite"
    image_mode: bool = True


@dataclass
class Settings:
    daily_snapshot: DailySnapshotConfig

    # env-derived
    solana_user_agent: str
    discord_webhook_url: str
    daily_snapshot_discord_webhook_url: str
    x_api_key: str
    x_api_secret: str
    x_access_token: str
    x_access_secret: str
    anthropic_api_key: str
    gemini_api_key: str
    log_level: str
    db_path: Path
    dry_run: bool


def _yaml_to_daily_snapshot(raw: dict[str, Any]) -> DailySnapshotConfig:
    ds_default = DailySnapshotConfig()
    ds_raw = raw.get("daily_snapshot", {}) or {}
    return DailySnapshotConfig(
        fetch_limit=ds_raw.get("fetch_limit", ds_default.fetch_limit),
        min_volume_24h_usd=ds_raw.get("min_volume_24h_usd", ds_default.min_volume_24h_usd),
        top_tokens_count=ds_raw.get("top_tokens_count", ds_default.top_tokens_count),
        hot_pairs_count=ds_raw.get("hot_pairs_count", ds_default.hot_pairs_count),
        whale_flows_count=ds_raw.get("whale_flows_count", ds_default.whale_flows_count),
        whale_min_volume_24h_usd=ds_raw.get(
            "whale_min_volume_24h_usd", ds_default.whale_min_volume_24h_usd
        ),
        whale_exclude_base_tokens=ds_raw.get(
            "whale_exclude_base_tokens", ds_default.whale_exclude_base_tokens
        ),
        display_aliases=ds_raw.get("display_aliases", {}) or {},
        label_max_chars=ds_raw.get("label_max_chars", ds_default.label_max_chars),
        discord_color=int(ds_raw.get("discord_color", ds_default.discord_color)),
        enable_discord=bool(ds_raw.get("enable_discord", ds_default.enable_discord)),
        enable_x=bool(ds_raw.get("enable_x", ds_default.enable_x)),
        enable_jp_translation=bool(
            ds_raw.get("enable_jp_translation", ds_default.enable_jp_translation)
        ),
        jp_translation_provider=ds_raw.get(
            "jp_translation_provider", ds_default.jp_translation_provider
        ),
        jp_translation_model=ds_raw.get(
            "jp_translation_model", ds_default.jp_translation_model
        ),
        image_mode=bool(ds_raw.get("image_mode", ds_default.image_mode)),
    )


def load_settings(
    settings_path: Path | str | None = None, env_path: Path | str | None = None
) -> Settings:
    settings_path = Path(settings_path or DEFAULT_SETTINGS_PATH)
    env_path = Path(env_path or DEFAULT_ENV_PATH)

    if env_path.exists():
        load_dotenv(env_path, override=False)

    raw: dict[str, Any] = {}
    if settings_path.exists():
        with settings_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    ds = _yaml_to_daily_snapshot(raw)

    db_path_str = os.getenv("DB_PATH", "./data/snapshot.db")
    db_path = Path(db_path_str)
    if not db_path.is_absolute():
        db_path = (PROJECT_ROOT / db_path).resolve()

    discord_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    daily_url = os.getenv("DAILY_SNAPSHOT_DISCORD_WEBHOOK_URL", "") or discord_url

    return Settings(
        daily_snapshot=ds,
        solana_user_agent=os.getenv(
            "SOLANA_USER_AGENT", "solana-daily-snapshot/0.1"
        ),
        discord_webhook_url=discord_url,
        daily_snapshot_discord_webhook_url=daily_url,
        x_api_key=os.getenv("X_API_KEY", ""),
        x_api_secret=os.getenv("X_API_SECRET", ""),
        x_access_token=os.getenv("X_ACCESS_TOKEN", ""),
        x_access_secret=os.getenv("X_ACCESS_SECRET", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        db_path=db_path,
        dry_run=os.getenv("DRY_RUN", "false").lower() in {"1", "true", "yes"},
    )
