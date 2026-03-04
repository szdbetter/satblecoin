from __future__ import annotations

from backend.service import StableYieldService


def test_build_curated_rows_filters_symbol_and_tvl() -> None:
    service = StableYieldService()

    pools = [
        {
            "project": "random-protocol",
            "chain": "Ethereum",
            "symbol": "USDC",
            "tvlUsd": 20_000_000,
            "apy": 3.2,
            "pool": "pool-1",
            "underlyingTokens": ["0xabc"],
        },
        {
            "project": "random-protocol",
            "chain": "Ethereum",
            "symbol": "USDT",
            "tvlUsd": 9_999_999,
            "apy": 3.2,
            "pool": "pool-2",
        },
        {
            "project": "random-protocol",
            "chain": "Ethereum",
            "symbol": "DAI",
            "tvlUsd": 30_000_000,
            "apy": 3.2,
            "pool": "pool-3",
        },
    ]

    rows = service._build_curated_rows(pools)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "USDC"
    assert rows[0]["tvl_usd"] >= 20_000_000


def test_mandatory_rows_have_placeholders_when_missing() -> None:
    service = StableYieldService()
    rows = service._build_mandatory_rows([])

    sources = {r["source"] for r in rows}
    assert sources == {"Aave", "Morpho", "Kamino", "MarginFi", "Spark", "Compound", "Lista", "Venus"}
    assert all("status" in r for r in rows)


def test_aave_special_market_is_filtered_out() -> None:
    service = StableYieldService()
    pools = [
        {
            "project": "aave-v3",
            "chain": "Ethereum",
            "symbol": "USDC",
            "tvlUsd": 100_000_000,
            "apyBase": 2.0,
            "pool": "main-pool",
            "poolMeta": None,
            "underlyingTokens": ["0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"],
        },
        {
            "project": "aave-v3",
            "chain": "Ethereum",
            "symbol": "USDC",
            "tvlUsd": 20_000_000,
            "apyBase": 3.5,
            "pool": "special-pool",
            "poolMeta": "lido-market",
            "underlyingTokens": ["0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"],
        },
    ]
    rows = service._build_mandatory_rows(pools)
    aave_rows = [r for r in rows if r.get("source") == "Aave" and r.get("project") == "aave-v3"]
    assert len(aave_rows) == 1
    assert aave_rows[0]["pool_id"] == "main-pool"


def test_is_available_record_filtering() -> None:
    service = StableYieldService()
    good = {
        "status": None,
        "deposit_apy_pct": 2.1,
        "token_entry_url": "https://example.com",
    }
    bad_status = {**good, "status": "当前未检索到可用池"}
    bad_apy = {**good, "deposit_apy_pct": None}
    bad_link = {**good, "token_entry_url": ""}

    assert service._is_available_record(good) is True
    assert service._is_available_record(bad_status) is False
    assert service._is_available_record(bad_apy) is False
    assert service._is_available_record(bad_link) is False


def test_normalize_daoge_link() -> None:
    service = StableYieldService()
    assert service._normalize_daoge_link("") == ""
    assert service._normalize_daoge_link("https://x.com/abc") == "https://x.com/abc"
    assert service._normalize_daoge_link("tutorials/USD1.html") == "https://web3daoge.com/tutorials/USD1.html"
