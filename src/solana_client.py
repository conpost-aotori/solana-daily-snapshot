"""GeckoTerminal client for Solana DEX pools (free, no auth).

Endpoints used:
- ``/networks/solana/pools``           — sorted by 24h USD volume (default)
- ``/networks/solana/pools?sort=h24_tx_count_desc`` — sorted by 24h tx count
- ``/networks/solana/trending_pools``  — algorithmic trending feed

Returns normalized rows shaped for ``daily_snapshot.collector.SnapshotRow``.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

GECKO_BASE = "https://api.geckoterminal.com/api/v2"
NETWORK = "solana"


class SolanaClientError(RuntimeError):
    pass


def _to_float(v: Any, default: float | None = None) -> float | None:
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class SolanaClient:
    """Thin wrapper around GeckoTerminal's free public API.

    Same context-manager interface as the original PolymarketClient so
    ``daily_snapshot.job`` can swap the call site with no other changes.
    """

    def __init__(self, *, user_agent: str = "solana-daily-snapshot/0.1",
                 timeout: float = 20.0, client: httpx.Client | None = None) -> None:
        self._owns_client = client is None
        headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self._client = client or httpx.Client(timeout=timeout, headers=headers)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "SolanaClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{GECKO_BASE}{path}"
        resp = self._client.get(url, params=params or {})
        if resp.status_code >= 400:
            log.warning("GeckoTerminal %s %s -> %s: %s",
                        path, params, resp.status_code, resp.text[:200])
            resp.raise_for_status()
        return resp.json()

    # ---- Public methods used by the collector ----

    def top_pools_by_volume(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """Pools sorted by 24h USD volume (default sort)."""
        raw = self._get(
            f"/networks/{NETWORK}/pools",
            {"include": "base_token,quote_token,dex", "page": 1},
        )
        return self._normalize(raw, source="top_volume")[:limit]

    def top_pools_by_tx_count(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """Pools sorted by 24h transaction count."""
        raw = self._get(
            f"/networks/{NETWORK}/pools",
            {
                "include": "base_token,quote_token,dex",
                "page": 1,
                "sort": "h24_tx_count_desc",
            },
        )
        return self._normalize(raw, source="top_tx")[:limit]

    def trending_pools(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """Algorithmic trending feed (24h)."""
        raw = self._get(
            f"/networks/{NETWORK}/trending_pools",
            {"include": "base_token,quote_token,dex", "duration": "24h"},
        )
        return self._normalize(raw, source="trending")[:limit]

    # ---- Internal: response → flat dict ----

    @staticmethod
    def _build_includes(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Index the JSON:API ``included`` array by ``id`` for relationship lookup."""
        return {item["id"]: item for item in raw.get("included", []) or []}

    def _normalize(self, raw: dict[str, Any], *, source: str) -> list[dict[str, Any]]:
        """Flatten JSON:API response → list of plain dicts the collector consumes."""
        includes = self._build_includes(raw)
        out: list[dict[str, Any]] = []
        for pool in raw.get("data", []) or []:
            attr = pool.get("attributes", {}) or {}
            rels = pool.get("relationships", {}) or {}

            base_id = (rels.get("base_token") or {}).get("data", {}).get("id")
            quote_id = (rels.get("quote_token") or {}).get("data", {}).get("id")
            dex_id = (rels.get("dex") or {}).get("data", {}).get("id")

            base = (includes.get(base_id) or {}).get("attributes") or {}
            quote = (includes.get(quote_id) or {}).get("attributes") or {}

            base_symbol = base.get("symbol") or ""
            quote_symbol = quote.get("symbol") or ""
            base_address = base.get("address") or ""
            base_name = base.get("name") or base_symbol

            vol = attr.get("volume_usd") or {}
            chg = attr.get("price_change_percentage") or {}
            txs = (attr.get("transactions") or {}).get("h24") or {}
            buys = txs.get("buys") or 0
            sells = txs.get("sells") or 0
            tx_count = int(buys) + int(sells)
            vol_h24 = _to_float(vol.get("h24"), 0.0) or 0.0
            avg_trade_usd = (vol_h24 / tx_count) if tx_count > 0 else 0.0

            # GeckoTerminal returns price change as a percent value (e.g. 10.5 = +10.5%).
            # We convert to fraction (0.105) so it matches the "delta" semantic the
            # renderer expects (multiplies by 100 to display).
            chg_h24_pct = _to_float(chg.get("h24"))
            chg_h24_frac = chg_h24_pct / 100 if chg_h24_pct is not None else None

            out.append({
                "pool_address": attr.get("address") or "",
                "pool_id": pool.get("id") or "",
                "pair_name": attr.get("name") or f"{base_symbol}/{quote_symbol}",
                "base_symbol": base_symbol,
                "base_name": base_name,
                "base_address": base_address,
                "quote_symbol": quote_symbol,
                "dex": dex_id or "",
                "price_usd": _to_float(attr.get("base_token_price_usd")),
                "price_change_24h_frac": chg_h24_frac,
                "volume_24h_usd": vol_h24,
                "tx_count_24h": tx_count,
                "buys_24h": int(buys),
                "sells_24h": int(sells),
                "buyers_24h": int(txs.get("buyers") or 0),
                "sellers_24h": int(txs.get("sellers") or 0),
                "avg_trade_usd": avg_trade_usd,
                "reserve_usd": _to_float(attr.get("reserve_in_usd"), 0.0) or 0.0,
                "fdv_usd": _to_float(attr.get("fdv_usd")),
                "source": source,
            })
        return out
