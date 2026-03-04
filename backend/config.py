from __future__ import annotations

from dataclasses import dataclass
import os

def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    cache_ttl_seconds: int = 300
    web3daoge_cache_ttl_seconds: int = int(os.getenv("WEB3DAOGE_CACHE_TTL_SECONDS", "300"))
    llama_pools_url: str = "https://yields.llama.fi/pools"
    web3daoge_data_url: str = "https://web3daoge.com/data.json"
    web3daoge_site_url: str = "https://web3daoge.com/"
    min_tvl_usd: float = 10_000_000
    stable_symbols: tuple[str, ...] = ("USDT", "USDC", "PYUSD", "USDG")
    okx_simple_earn_url: str = "https://www.okx.com/en-us/earn/simple-earn"
    okx_onchain_api: str = "https://www.okx.com/priapi/v1/earn/onchain-earn/all-products"
    enable_okx: bool = _env_flag("ENABLE_OKX", "0")
    binance_simple_earn_flexible_url: str = "https://api.binance.com/sapi/v1/simple-earn/flexible/list"
    binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
    binance_api_secret: str = os.getenv("BINANCE_API_SECRET", "")


SETTINGS = Settings()
