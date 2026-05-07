"""Format the snapshot for Discord (embed) and X (280-char tweet).

Image mode is the default (the PNG card carries the data); these are
fallbacks for when rendering fails.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .collector import SnapshotRow

JST = ZoneInfo("Asia/Tokyo")
DISCORD_COLOR_DEFAULT = 0x9945FF  # Solana purple


def _label(row: SnapshotRow, aliases: dict[str, str], max_chars: int = 40) -> str:
    if row.slug and row.slug in aliases:
        return aliases[row.slug]
    q = row.question or "(unknown)"
    return q if len(q) <= max_chars else q[: max_chars - 1].rstrip() + "…"


def _fmt_price(p: float | None) -> str:
    if p is None:
        return "—"
    if p >= 100:
        return f"${p:,.2f}"
    if p >= 1:
        return f"${p:.3f}"
    if p >= 0.01:
        return f"${p:.4f}"
    if p >= 0.0001:
        return f"${p:.6f}"
    return f"${p:.2e}"


def _fmt_delta_pct(d: float | None) -> str:
    if d is None:
        return "—"
    pct = d * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


# ---------- Discord ----------

def build_discord_embed(
    *,
    snapshot_date: datetime,
    top_tokens: list[SnapshotRow],
    hot_pairs: list[SnapshotRow],
    whale_flows: list[SnapshotRow],
    aliases: dict[str, str] | None = None,
    color: int = DISCORD_COLOR_DEFAULT,
    footer_text: str = "Auto-generated · Data via GeckoTerminal",
) -> dict[str, Any]:
    aliases = aliases or {}
    date_str = snapshot_date.astimezone(JST).strftime("%Y-%m-%d")

    def _block(name: str, rows: list[SnapshotRow]) -> dict[str, Any] | None:
        if not rows:
            return None
        lines = [
            f"• {_label(r, aliases)}  **{_fmt_price(r.yes_price)}**  {_fmt_delta_pct(r.one_day_change)}"
            for r in rows
        ]
        return {"name": name, "value": "\n".join(lines), "inline": False}

    fields: list[dict[str, Any]] = []
    for block in (
        _block("🔥 Top tokens (24h volume)", top_tokens),
        _block("⚡ Hot pairs (trending)", hot_pairs),
        _block("🐋 Whale flows (avg $/trade)", whale_flows),
    ):
        if block is not None:
            fields.append(block)

    return {
        "title": "☀ Solana Daily Snapshot",
        "description": f"**{date_str} (JST)**",
        "color": color,
        "fields": fields,
        "footer": {"text": footer_text},
        "timestamp": snapshot_date.astimezone(JST).isoformat(),
    }


# ---------- X (Twitter) ----------

X_MAX_CHARS = 280


def build_tweet(
    *,
    snapshot_date: datetime,
    top_tokens: list[SnapshotRow],
    aliases: dict[str, str] | None = None,
    hashtags: str = "#Solana #DeFi",
) -> str:
    """Compress to a 280-char tweet — top 3 tokens by 24h volume."""
    aliases = aliases or {}
    date_str = snapshot_date.astimezone(JST).strftime("%m/%d JST")
    header = f"☀ Solana Daily {date_str}\n🔥 Top tokens (24h volume)"

    def render(rows: list[SnapshotRow], label_max: int) -> str:
        body = [
            f"• {_label(r, aliases, max_chars=label_max)} {_fmt_price(r.yes_price)} {_fmt_delta_pct(r.one_day_change)}"
            for r in rows
        ]
        parts = [header, *body]
        if hashtags:
            parts.append(hashtags)
        return "\n".join(parts)

    for label_max in (40, 32, 24, 20, 16):
        text = render(top_tokens, label_max)
        if len(text) <= X_MAX_CHARS:
            return text
    for label_max in (32, 24, 20, 16):
        text = render(top_tokens[: max(1, len(top_tokens) - 1)], label_max)
        if len(text) <= X_MAX_CHARS:
            return text
    return render(top_tokens[:1], 16)[:X_MAX_CHARS]
