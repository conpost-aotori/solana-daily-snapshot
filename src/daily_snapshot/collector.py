"""Daily snapshot data collection for Solana DEX pools.

Three sections, fetched with three GeckoTerminal calls:
- ``top_tokens``  — highest 24h USD volume, deduped per base token
- ``hot_pairs``   — algorithmic trending pools (24h window)
- ``whale_flows`` — high-volume pools sorted by avg trade size (a free-API
  proxy for whale activity: large $/tx implies fewer-but-larger trades)

The shared row shape (``SnapshotRow``) is intentionally close to the
prediction-market original so the renderer / formatter stay reusable —
``yes_price`` becomes the token's USD price, ``one_day_change`` becomes
the 24h % change as a fraction.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from ..solana_client import SolanaClient

log = logging.getLogger(__name__)


@dataclass
class SnapshotRow:
    """One row in the snapshot card.

    Field meanings overloaded for the Solana use case so the existing
    renderer (which expects ``yes_price`` / ``one_day_change`` /
    ``volume_24h_usd``) needs no changes.
    """
    market_id: str           # pool_address
    slug: str | None         # base token symbol (used as JP-translation cache key)
    question: str            # display label, e.g. "WIF / SOL · Raydium"
    yes_price: float | None  # base token USD price (rendered as $X)
    one_day_change: float | None  # 24h price change as fraction (0.10 = +10%)
    volume_24h_usd: float
    tag_slugs: list[str]     # ["solana", dex, source_section]
    category: str | None     # "top_tokens" | "hot_pairs" | "whale_flows"
    event_slug: str | None = None  # base token address, used for dedup
    event_title: str | None = None
    # Solana-specific extras (renderer ignores these but kept for audit/db):
    base_symbol: str | None = None
    quote_symbol: str | None = None
    dex: str | None = None
    tx_count_24h: int = 0
    avg_trade_usd: float = 0.0


def _row_from_pool(pool: dict, *, category: str) -> SnapshotRow:
    base = pool.get("base_symbol") or "?"
    quote = pool.get("quote_symbol") or ""
    dex = pool.get("dex") or ""
    pair = f"{base} / {quote}" if quote else base
    label = f"{pair} · {dex}" if dex else pair
    return SnapshotRow(
        market_id=pool.get("pool_address") or pool.get("pool_id") or pair,
        slug=base.lower() if base != "?" else None,
        question=label,
        yes_price=pool.get("price_usd"),
        one_day_change=pool.get("price_change_24h_frac"),
        volume_24h_usd=float(pool.get("volume_24h_usd") or 0.0),
        tag_slugs=["solana", dex, pool.get("source") or ""],
        category=category,
        event_slug=pool.get("base_address") or None,
        event_title=pool.get("base_name") or base,
        base_symbol=base,
        quote_symbol=quote,
        dex=dex,
        tx_count_24h=int(pool.get("tx_count_24h") or 0),
        avg_trade_usd=float(pool.get("avg_trade_usd") or 0.0),
    )


def _dedup_by_base_token(rows: list[SnapshotRow]) -> list[SnapshotRow]:
    """Keep the first occurrence per base token (sort first to pick the winner)."""
    seen: set[str] = set()
    out: list[SnapshotRow] = []
    for r in rows:
        key = (r.event_slug or r.base_symbol or r.market_id).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def collect_top_tokens(
    client: SolanaClient,
    *,
    limit: int = 3,
    fetch_limit: int = 20,
    min_volume_24h_usd: float = 0,
) -> list[SnapshotRow]:
    """Section 1: highest 24h volume, deduped per base token."""
    raw = client.top_pools_by_volume(limit=fetch_limit)
    rows = [_row_from_pool(p, category="top_tokens") for p in raw]
    rows = [r for r in rows if r.volume_24h_usd >= min_volume_24h_usd]
    rows.sort(key=lambda r: r.volume_24h_usd, reverse=True)
    return _dedup_by_base_token(rows)[:limit]


def collect_hot_pairs(
    client: SolanaClient,
    *,
    limit: int = 3,
    fetch_limit: int = 20,
    min_volume_24h_usd: float = 0,
) -> list[SnapshotRow]:
    """Section 2: algorithmic trending feed."""
    raw = client.trending_pools(limit=fetch_limit)
    rows = [_row_from_pool(p, category="hot_pairs") for p in raw]
    rows = [r for r in rows if r.volume_24h_usd >= min_volume_24h_usd]
    return _dedup_by_base_token(rows)[:limit]


def collect_whale_flows(
    client: SolanaClient,
    *,
    limit: int = 3,
    fetch_limit: int = 20,
    min_volume_24h_usd: float = 1_000_000,
    exclude_base_tokens: Iterable[str] = (),
) -> list[SnapshotRow]:
    """Section 3: highest avg-trade-size, filtered to liquid pools.

    Uses ``volume / tx_count`` as a proxy for whale activity.  Stablecoin
    pairs (USDC/USDT/SOL) dominate this metric so they're excluded by
    default — adjust via ``exclude_base_tokens``.
    """
    raw = client.top_pools_by_tx_count(limit=fetch_limit)
    excluded = {s.lower() for s in exclude_base_tokens}
    rows = [_row_from_pool(p, category="whale_flows") for p in raw]
    rows = [
        r for r in rows
        if r.volume_24h_usd >= min_volume_24h_usd
        and (r.base_symbol or "").lower() not in excluded
    ]
    rows.sort(key=lambda r: r.avg_trade_usd, reverse=True)
    return _dedup_by_base_token(rows)[:limit]


def collect_snapshot(
    client: SolanaClient,
    *,
    top_tokens_count: int = 3,
    hot_pairs_count: int = 3,
    whale_flows_count: int = 3,
    fetch_limit: int = 20,
    min_volume_24h_usd: float = 0,
    whale_min_volume_24h_usd: float = 1_000_000,
    whale_exclude_base_tokens: Iterable[str] = ("USDC", "USDT", "SOL", "WSOL"),
) -> tuple[list[SnapshotRow], list[SnapshotRow], list[SnapshotRow]]:
    """Fetch all three sections in one call. Returns (top_tokens, hot_pairs, whale_flows)."""
    top_tokens = collect_top_tokens(
        client, limit=top_tokens_count, fetch_limit=fetch_limit,
        min_volume_24h_usd=min_volume_24h_usd,
    )
    hot_pairs = collect_hot_pairs(
        client, limit=hot_pairs_count, fetch_limit=fetch_limit,
        min_volume_24h_usd=min_volume_24h_usd,
    )
    whale_flows = collect_whale_flows(
        client, limit=whale_flows_count, fetch_limit=fetch_limit,
        min_volume_24h_usd=whale_min_volume_24h_usd,
        exclude_base_tokens=whale_exclude_base_tokens,
    )
    log.info("snapshot: %d top / %d hot / %d whale",
             len(top_tokens), len(hot_pairs), len(whale_flows))
    return top_tokens, hot_pairs, whale_flows
