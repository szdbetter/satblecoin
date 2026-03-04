from __future__ import annotations

import hmac
import json
import re
import time
from hashlib import sha256
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.parse import urljoin
from threading import Lock
from typing import Any

import requests

from .config import SETTINGS

PROJECT_SOURCE_MAP = {
    "aave-v3": "Aave",
    "morpho-v1": "Morpho",
    "kamino-lend": "Kamino",
    "marginfi-lending": "MarginFi",
    "marginfi-lst": "MarginFi",
    "sparklend": "Spark",
    "spark-savings": "Spark",
    "compound-v3": "Compound",
    "lista-lending": "Lista",
    "venus-core-pool": "Venus",
}

SOURCE_WEBSITE_MAP = {
    "Aave": "https://app.aave.com/",
    "Morpho": "https://app.morpho.org/earn",
    "Kamino": "https://app.kamino.finance/",
    "MarginFi": "https://app.marginfi.com/",
    "DeFiLlama-精选": "https://defillama.com/yields",
    "OKX钱包-简单赚币": "https://www.okx.com/en-us/earn/simple-earn",
    "OKX钱包-Onchain": "https://www.okx.com/en-us/earn/onchain-earn",
    "Binance理财": "https://www.binance.com/en/earn",
    "Binance Web3钱包-公开": "https://www.binance.com/en/web3wallet",
    "Spark": "https://app.spark.fi/markets",
    "Compound": "https://compound.finance/markets",
    "Lista": "https://lista.org/",
    "Venus": "https://venus.io/core-pool",
}

CHAIN_SLUG_MAP = {
    "ethereum": "ethereum",
    "arbitrum": "arbitrum",
    "optimism": "optimism",
    "polygon": "polygon",
    "avalanche": "avalanche",
    "base": "base",
    "bsc": "bnb",
    "linea": "linea",
    "sonic": "sonic",
    "scroll": "scroll",
    "celo": "celo",
    "zksync era": "zksync",
    "solana": "solana",
}

AAVE_MARKET_NAME_MAP = {
    "ethereum": "proto_mainnet_v3",
    "arbitrum": "proto_arbitrum_v3",
    "optimism": "proto_optimism_v3",
    "polygon": "proto_polygon_v3",
    "avalanche": "proto_avalanche_v3",
    "base": "proto_base_v3",
    "bsc": "proto_bnb_v3",
    "linea": "proto_linea_v3",
    "sonic": "proto_sonic_v3",
    "scroll": "proto_scroll_v3",
    "celo": "proto_celo_v3",
    "zksync era": "proto_zksync_v3",
}


@dataclass
class CacheEntry:
    created_at_epoch: float
    payload: dict[str, Any]


class StableYieldService:
    def __init__(self) -> None:
        self._cache: CacheEntry | None = None
        self._daoge_cache: CacheEntry | None = None
        self._lock = Lock()

    def get_payload(self, force_refresh: bool = False) -> dict[str, Any]:
        with self._lock:
            now_epoch = time.time()
            if (
                not force_refresh
                and self._cache is not None
                and now_epoch - self._cache.created_at_epoch < SETTINGS.cache_ttl_seconds
            ):
                return self._cache.payload

            payload = self._build_payload(now_epoch=now_epoch)
            self._cache = CacheEntry(created_at_epoch=now_epoch, payload=payload)
            return payload

    def get_daoge_payload(self, force_refresh: bool = False) -> dict[str, Any]:
        with self._lock:
            now_epoch = time.time()
            if (
                not force_refresh
                and self._daoge_cache is not None
                and now_epoch - self._daoge_cache.created_at_epoch < SETTINGS.web3daoge_cache_ttl_seconds
            ):
                return self._daoge_cache.payload

            payload = self._build_daoge_payload(now_epoch=now_epoch)
            self._daoge_cache = CacheEntry(created_at_epoch=now_epoch, payload=payload)
            return payload

    def _build_payload(self, now_epoch: float) -> dict[str, Any]:
        pools = self._fetch_llama_pools()

        mandatory_rows = self._build_mandatory_rows(pools)
        curated_rows = self._build_curated_rows(pools)
        external_rows, connector_status = self._build_external_rows(now_epoch=now_epoch, pools=pools)

        merged_rows = mandatory_rows + curated_rows + external_rows
        all_rows = sorted(
            [row for row in merged_rows if self._is_available_record(row)],
            key=lambda x: (x["source"], -x["tvl_usd"]),
        )

        generated_at = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat()

        return {
            "generated_at_utc": generated_at,
            "cache_ttl_seconds": SETTINGS.cache_ttl_seconds,
            "records": all_rows,
            "meta": {
                "record_count": len(all_rows),
                "mandatory_record_count": len(mandatory_rows),
                "curated_record_count": len(curated_rows),
                "external_record_count": len(external_rows),
                "raw_record_count": len(merged_rows),
                "sources": sorted({row["source"] for row in all_rows}),
                "connector_status": connector_status,
                "note": "收益率与TVL来自 DeFiLlama Yields API 实时数据；入口链接优先协议官方，缺失时回退到DeFiLlama池页面。",
            },
        }

    def _build_daoge_payload(self, now_epoch: float) -> dict[str, Any]:
        response = requests.get(
            SETTINGS.web3daoge_data_url,
            params={"t": int(now_epoch * 1000)},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload if isinstance(payload, list) else []

        normalized_rows: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            tutorial = str(item.get("教程链接") or "").strip()
            normalized_rows.append(
                {
                    "平台": item.get("平台") or "",
                    "币种": item.get("币种") or "",
                    "年化（APY）": item.get("年化（APY）") or "",
                    "单个账户限额": item.get("单个账户限额") or "",
                    "开始时间": item.get("开始时间") or "",
                    "结束时间": item.get("结束时间") or "",
                    "是否锁仓": item.get("是否锁仓") or "",
                    "派息时间": item.get("派息时间") or "",
                    "教程链接": self._normalize_daoge_link(tutorial),
                }
            )

        generated_at = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat()
        return {
            "generated_at_utc": generated_at,
            "cache_ttl_seconds": SETTINGS.web3daoge_cache_ttl_seconds,
            "records": normalized_rows,
            "meta": {
                "record_count": len(normalized_rows),
                "source": "web3daoge.com/data.json",
                "site": SETTINGS.web3daoge_site_url,
            },
        }

    @staticmethod
    def _normalize_daoge_link(link: str) -> str:
        if not link:
            return ""
        if link.startswith("http://") or link.startswith("https://"):
            return link
        return urljoin(SETTINGS.web3daoge_site_url, link.lstrip("/"))

    @staticmethod
    def _is_available_record(record: dict[str, Any]) -> bool:
        # 统一过滤不可用状态：
        # 1) 显式状态异常（如“未检索到可用池”）
        # 2) 无存款APY
        # 3) 无可用入口链接
        status = record.get("status")
        if isinstance(status, str) and status.strip():
            return False
        if record.get("deposit_apy_pct") is None:
            return False
        if not record.get("token_entry_url"):
            return False
        return True

    def _fetch_llama_pools(self) -> list[dict[str, Any]]:
        response = requests.get(SETTINGS.llama_pools_url, timeout=30)
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", [])

    def _build_external_rows(self, now_epoch: float, pools: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
        rows: list[dict[str, Any]] = []
        status: dict[str, str] = {}

        if SETTINGS.enable_okx:
            try:
                okx_simple_rows = self._fetch_okx_simple_earn_rows()
                rows.extend(okx_simple_rows)
                status["okx_simple_earn"] = f"ok:{len(okx_simple_rows)}"
            except Exception as exc:  # noqa: BLE001
                status["okx_simple_earn"] = f"error:{type(exc).__name__}"

            try:
                okx_onchain_rows = self._fetch_okx_onchain_rows()
                rows.extend(okx_onchain_rows)
                status["okx_onchain_earn"] = f"ok:{len(okx_onchain_rows)}"
            except Exception as exc:  # noqa: BLE001
                status["okx_onchain_earn"] = f"error:{type(exc).__name__}"
        else:
            status["okx_simple_earn"] = "disabled"
            status["okx_onchain_earn"] = "disabled"

        if not SETTINGS.binance_api_key or not SETTINGS.binance_api_secret:
            status["binance_simple_earn"] = "disabled:requires_api_key(USER_DATA)"
        else:
            try:
                binance_rows = self._fetch_binance_rows(now_epoch=now_epoch)
                rows.extend(binance_rows)
                status["binance_simple_earn"] = f"ok:{len(binance_rows)}"
            except Exception as exc:  # noqa: BLE001
                status["binance_simple_earn"] = f"error:{type(exc).__name__}"

        try:
            binance_web3_rows = self._build_binance_web3_public_rows(pools=pools)
            rows.extend(binance_web3_rows)
            status["binance_web3_public"] = f"ok:{len(binance_web3_rows)}"
        except Exception as exc:  # noqa: BLE001
            status["binance_web3_public"] = f"error:{type(exc).__name__}"

        return rows, status

    def _fetch_okx_simple_earn_rows(self) -> list[dict[str, Any]]:
        response = requests.get(SETTINGS.okx_simple_earn_url, timeout=30)
        response.raise_for_status()
        html = response.text
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.S)

        payload_obj: dict[str, Any] | None = None
        for script in scripts:
            if "simpleEarnData" not in script:
                continue
            try:
                maybe_json = json.loads(script)
            except json.JSONDecodeError:
                continue
            payload_obj = maybe_json
            break

        if payload_obj is None:
            return []

        currencies = (
            payload_obj.get("appContext", {})
            .get("initialProps", {})
            .get("preData", {})
            .get("simpleEarnStore", {})
            .get("simpleEarnData", {})
            .get("allProducts", {})
            .get("currencies", [])
        )

        rows: list[dict[str, Any]] = []
        for item in currencies:
            symbol = (item.get("investCurrency", {}) or {}).get("currencyName", "")
            if not self._is_target_symbol(symbol):
                continue

            rate_num = (
                item.get("rate", {})
                .get("rateNum", {})
                .get("value", [None])
            )
            apy = self._safe_max_number(rate_num)
            if apy is None:
                continue

            redirect_url = item.get("redirectUrl") or "/en-us/earn/simple-earn"
            # OKX 的 /earn/subscribe 深链在公开环境会 404，回退到可访问的 Simple Earn 页并带 token。
            redirect_url = f"https://www.okx.com/en-us/earn/simple-earn?token={symbol}"

            rows.append(
                self._build_external_record(
                    source="OKX钱包-简单赚币",
                    chain="CeFi",
                    symbol=symbol,
                    deposit_apy=apy,
                    borrow_apy=None,
                    tvl_usd=float(item.get("valuationUSD") or 0.0),
                    token_entry_url=redirect_url,
                    firewall_name="Simple Earn",
                    project="okx-simple-earn",
                )
            )
        return rows

    def _fetch_okx_onchain_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for symbol in SETTINGS.stable_symbols:
            params = {
                "pageNum": 1,
                "pageSize": 50,
                "sorting": "NORMAL",
                "token": symbol,
            }
            response = requests.get(SETTINGS.okx_onchain_api, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()
            products = payload.get("data", {}).get("all", [])
            for item in products:
                token_symbol = (item.get("investCurrency", {}) or {}).get("currencyName", "")
                if not self._is_target_symbol(token_symbol):
                    continue
                apy_vals = item.get("rate", {}).get("rate", {}).get("value", [])
                apy = self._safe_max_number(apy_vals)
                if apy is None:
                    continue
                protocol_name = (item.get("protocol", {}) or {}).get("name", "Onchain")
                # 同理，订阅深链对未登录公开访问常 404，使用可访问的 onchain 页面入口。
                redirect_url = f"https://www.okx.com/en-us/earn/onchain-earn?token={token_symbol}"
                rows.append(
                    self._build_external_record(
                        source="OKX钱包-Onchain",
                        chain="Onchain",
                        symbol=token_symbol,
                        deposit_apy=apy,
                        borrow_apy=None,
                        tvl_usd=float(item.get("marketCap") or 0.0),
                        token_entry_url=str(redirect_url),
                        firewall_name=protocol_name,
                        project="okx-onchain-earn",
                    )
                )
        return rows

    def _fetch_binance_rows(self, now_epoch: float) -> list[dict[str, Any]]:
        # Binance Simple Earn 官方接口需要 API Key + 签名。
        # 未配置密钥时跳过，避免返回错误数据。
        if not SETTINGS.binance_api_key or not SETTINGS.binance_api_secret:
            return []

        query = {
            "current": 1,
            "size": 100,
            "timestamp": int(now_epoch * 1000),
        }
        query_string = urlencode(query)
        signature = hmac.new(
            SETTINGS.binance_api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            sha256,
        ).hexdigest()
        params = {**query, "signature": signature}
        headers = {"X-MBX-APIKEY": SETTINGS.binance_api_key}

        response = requests.get(
            SETTINGS.binance_simple_earn_flexible_url,
            params=params,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        rows_data = payload.get("rows", [])

        rows: list[dict[str, Any]] = []
        for item in rows_data:
            symbol = (item.get("asset") or "").upper()
            if not self._is_target_symbol(symbol):
                continue
            apy = self._safe_float(item.get("latestAnnualPercentageRate"))
            if apy is None:
                continue
            rows.append(
                self._build_external_record(
                    source="Binance理财",
                    chain="CeFi",
                    symbol=symbol,
                    deposit_apy=apy,
                    borrow_apy=None,
                    tvl_usd=0.0,
                    token_entry_url="https://www.binance.com/en/earn",
                    firewall_name=f"状态:{item.get('status', 'N/A')}",
                    project="binance-simple-earn",
                )
            )
        return rows

    def _build_binance_web3_public_rows(self, pools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # 免费公开口径：从公开 DeFi 数据中提取 Binance Web3 钱包常见稳定币理财协议。
        web3_projects = {"lista-lending", "venus-core-pool", "morpho-v1"}
        rows: list[dict[str, Any]] = []

        for pool in pools:
            project = (pool.get("project") or "").strip().lower()
            if project not in web3_projects:
                continue
            symbol = (pool.get("symbol") or "").upper()
            if not self._is_target_symbol(symbol):
                continue

            tvl = float(pool.get("tvlUsd") or 0.0)
            deposit_apy = pool.get("apyBase")
            if deposit_apy is None:
                deposit_apy = pool.get("apy")
            borrow_apy = pool.get("apyBaseBorrow")

            src = PROJECT_SOURCE_MAP.get(project, "N/A")
            token_entry_url = self._build_token_entry_url(source=src, pool=pool)
            firewall_name = f"Binance Web3可用池:{src}"
            rows.append(
                {
                    "source": "Binance Web3钱包-公开",
                    "project": project,
                    "chain": (pool.get("chain") or "").strip(),
                    "symbol": symbol,
                    "tvl_usd": tvl,
                    "deposit_apy_pct": self._round_num(deposit_apy),
                    "borrow_apy_pct": self._round_num(borrow_apy),
                    "net_spread_pct": self._round_num(
                        (deposit_apy - borrow_apy)
                        if isinstance(deposit_apy, (int, float)) and isinstance(borrow_apy, (int, float))
                        else None
                    ),
                    "website_url": SOURCE_WEBSITE_MAP["Binance Web3钱包-公开"],
                    "pool_id": pool.get("pool"),
                    "pool_detail_url": f"https://defillama.com/yields/pool/{pool.get('pool')}" if pool.get("pool") else None,
                    "token_entry_url": token_entry_url,
                    "data_source": "DeFiLlama Yields API (Public, no API key)",
                    "market_scope": "Binance Web3公开池",
                    "firewall_name": firewall_name,
                }
            )
        return rows

    def _build_external_record(
        self,
        source: str,
        chain: str,
        symbol: str,
        deposit_apy: float | None,
        borrow_apy: float | None,
        tvl_usd: float,
        token_entry_url: str,
        firewall_name: str,
        project: str,
    ) -> dict[str, Any]:
        return {
            "source": source,
            "project": project,
            "chain": chain,
            "symbol": symbol,
            "tvl_usd": float(tvl_usd or 0.0),
            "deposit_apy_pct": self._round_num(deposit_apy),
            "borrow_apy_pct": self._round_num(borrow_apy),
            "net_spread_pct": None,
            "website_url": SOURCE_WEBSITE_MAP.get(source),
            "pool_id": None,
            "pool_detail_url": None,
            "token_entry_url": token_entry_url,
            "data_source": "Exchange/Wallet Public API",
            "market_scope": "活动",
            "firewall_name": firewall_name,
        }

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _safe_max_number(self, values: Any) -> float | None:
        if not isinstance(values, list):
            return self._safe_float(values)
        parsed = [self._safe_float(v) for v in values]
        parsed = [v for v in parsed if v is not None]
        if not parsed:
            return None
        return max(parsed)

    def _is_target_symbol(self, symbol: str) -> bool:
        symbol_u = (symbol or "").upper()
        return symbol_u in SETTINGS.stable_symbols

    def _base_record(self, pool: dict[str, Any], source: str) -> dict[str, Any]:
        chain = (pool.get("chain") or "").strip()
        symbol = (pool.get("symbol") or "").upper()
        pool_id = pool.get("pool") or ""

        deposit_apy = pool.get("apyBase")
        if deposit_apy is None:
            deposit_apy = pool.get("apy")

        borrow_apy = pool.get("apyBaseBorrow")

        website_url = SOURCE_WEBSITE_MAP.get(source, "https://defillama.com/yields")
        token_entry_url = self._build_token_entry_url(source=source, pool=pool)

        record = {
            "source": source,
            "project": pool.get("project"),
            "chain": chain,
            "symbol": symbol,
            "tvl_usd": float(pool.get("tvlUsd") or 0.0),
            "deposit_apy_pct": self._round_num(deposit_apy),
            "borrow_apy_pct": self._round_num(borrow_apy),
            "net_spread_pct": self._round_num(
                (deposit_apy - borrow_apy)
                if isinstance(deposit_apy, (int, float)) and isinstance(borrow_apy, (int, float))
                else None
            ),
            "website_url": website_url,
            "pool_id": pool_id,
            "pool_detail_url": f"https://defillama.com/yields/pool/{pool_id}" if pool_id else None,
            "token_entry_url": token_entry_url,
            "data_source": "DeFiLlama Yields API",
            "market_scope": "主市场" if pool.get("poolMeta") in (None, "", "null") else f"子市场:{pool.get('poolMeta')}",
            "firewall_name": "主市场" if pool.get("poolMeta") in (None, "", "null") else str(pool.get("poolMeta")),
        }
        return record

    @staticmethod
    def _round_num(value: Any) -> float | None:
        if not isinstance(value, (int, float)):
            return None
        return round(float(value), 6)

    def _build_token_entry_url(self, source: str, pool: dict[str, Any]) -> str:
        pool_id = pool.get("pool")
        fallback = f"https://defillama.com/yields/pool/{pool_id}" if pool_id else "https://defillama.com/yields"

        if source == "Aave":
            chain = (pool.get("chain") or "").strip().lower()
            market_name = AAVE_MARKET_NAME_MAP.get(chain)
            token_addr = None
            underlying_tokens = pool.get("underlyingTokens") or []
            if underlying_tokens:
                token_addr = underlying_tokens[0]
            if market_name and token_addr:
                return (
                    "https://app.aave.com/reserve-overview/"
                    f"?underlyingAsset={token_addr}&marketName={market_name}"
                )
            return "https://app.aave.com/"

        if source == "Morpho":
            chain = CHAIN_SLUG_MAP.get((pool.get("chain") or "").strip().lower(), "ethereum")
            symbol = (pool.get("symbol") or "").upper()
            return f"https://app.morpho.org/{chain}/earn?asset={symbol}"

        if source == "Kamino":
            symbol = (pool.get("symbol") or "").upper()
            return f"https://app.kamino.finance/lend?asset={symbol}"

        if source == "MarginFi":
            symbol = (pool.get("symbol") or "").upper()
            return f"https://app.marginfi.com/?asset={symbol}"

        if source == "Spark":
            return "https://app.spark.fi/markets"

        if source == "Compound":
            return "https://compound.finance/markets"

        if source == "Lista":
            return "https://lista.org/"

        if source == "Venus":
            return "https://venus.io/core-pool"

        return fallback

    def _build_mandatory_rows(self, pools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        target_projects = {
            "aave-v3",
            "morpho-v1",
            "kamino-lend",
            "marginfi-lending",
            "sparklend",
            "spark-savings",
            "compound-v3",
            "lista-lending",
            "venus-core-pool",
        }

        for pool in pools:
            project = (pool.get("project") or "").strip().lower()
            if project not in target_projects:
                continue

            # Aave 同链同币存在主市场/子市场（如 lido-market, horizon-market）。
            # 为与官网主界面口径一致，默认仅保留主市场（poolMeta 为空）。
            if project == "aave-v3" and pool.get("poolMeta") not in (None, "", "null"):
                continue

            symbol = pool.get("symbol") or ""
            if not self._is_target_symbol(symbol):
                continue

            source = PROJECT_SOURCE_MAP.get(project)
            if source is None:
                continue
            rows.append(self._base_record(pool=pool, source=source))

        available_sources = {row["source"] for row in rows}
        for must_have_source in ["Aave", "Morpho", "Kamino", "MarginFi", "Spark", "Compound", "Lista", "Venus"]:
            if must_have_source in available_sources:
                continue
            rows.append(
                {
                    "source": must_have_source,
                    "project": None,
                    "chain": None,
                    "symbol": None,
                    "tvl_usd": 0.0,
                    "deposit_apy_pct": None,
                    "borrow_apy_pct": None,
                    "net_spread_pct": None,
                    "website_url": SOURCE_WEBSITE_MAP[must_have_source],
                    "pool_id": None,
                    "pool_detail_url": None,
                    "token_entry_url": SOURCE_WEBSITE_MAP[must_have_source],
                    "data_source": "DeFiLlama Yields API",
                    "firewall_name": "N/A",
                    "status": "当前未检索到 USDT/USDC 可用池",
                }
            )

        return rows

    def _build_curated_rows(self, pools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        excluded_projects = {
            "aave-v3",
            "morpho-v1",
            "kamino-lend",
            "marginfi-lending",
            "marginfi-lst",
            "sparklend",
            "spark-savings",
            "compound-v3",
            "lista-lending",
            "venus-core-pool",
        }

        for pool in pools:
            project = (pool.get("project") or "").strip().lower()
            if project in excluded_projects:
                continue
            symbol = pool.get("symbol") or ""
            if not self._is_target_symbol(symbol):
                continue
            tvl = float(pool.get("tvlUsd") or 0.0)
            if tvl < SETTINGS.min_tvl_usd:
                continue

            row = self._base_record(pool=pool, source="DeFiLlama-精选")
            rows.append(row)

        rows.sort(key=lambda x: x["tvl_usd"], reverse=True)
        return rows


SERVICE = StableYieldService()
