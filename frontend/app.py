from __future__ import annotations

import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
from streamlit_autorefresh import st_autorefresh
from backend.service import SERVICE

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
BJ_TZ = ZoneInfo("Asia/Shanghai")

st.set_page_config(page_title="稳定币收益对比仪表盘", layout="wide")
st_autorefresh(interval=60_000, key="auto_refresh_60s")

st.markdown(
    """
<style>
.block-container {
  max-width: 100% !important;
  padding-top: 1rem;
  padding-bottom: 1rem;
}
.app-shell {
  background: linear-gradient(180deg, #f7fbff 0%, #ffffff 45%, #f8fafc 100%);
  border: 1px solid #e8eef6;
  border-radius: 18px;
  padding: 18px 18px 10px 18px;
  box-shadow: 0 10px 30px rgba(10, 35, 66, 0.06);
}
.kpi-card {
  background: #ffffff;
  border: 1px solid #e8eef6;
  border-radius: 14px;
  padding: 12px 14px;
  box-shadow: 0 3px 10px rgba(15, 23, 42, 0.04);
}
.kpi-title {
  font-size: 12px;
  color: #5b6b82;
  margin-bottom: 4px;
}
.kpi-val {
  font-size: 24px;
  font-weight: 700;
  color: #13233a;
}
.panel {
  background: #ffffff;
  border: 1px solid #e8eef6;
  border-radius: 14px;
  padding: 10px 12px;
  margin-bottom: 10px;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown('<div class="app-shell">', unsafe_allow_html=True)
st.title("全网稳定币收益对比（USDT / USDC）")
st.caption("卡片化表格视图。时间统一北京时间。")

left, mid, right = st.columns([1.1, 2.4, 2.5])
force_refresh = left.button("手动刷新（强制）", type="primary", use_container_width=True)


def fetch_data(force: bool) -> dict:
    params = {"force_refresh": "true"} if force else None
    try:
        response = requests.get(f"{API_BASE_URL}/api/yields", params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception:
        # Streamlit Cloud 常见场景：未单独部署后端服务，回退到本地进程直接取数。
        return SERVICE.get_payload(force_refresh=force)


def fetch_web3daoge_data(force: bool) -> dict:
    params = {"force_refresh": "true"} if force else None
    try:
        response = requests.get(f"{API_BASE_URL}/api/web3daoge", params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception:
        return SERVICE.get_daoge_payload(force_refresh=force)


def parse_apy_value(value: object) -> float:
    text = str(value or "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return float("-inf")
    try:
        return float(match.group(0))
    except ValueError:
        return float("-inf")


try:
    payload = fetch_data(force=force_refresh)
except Exception as exc:
    st.error(f"数据拉取失败：{exc}")
    st.stop()

try:
    web3daoge_payload = fetch_web3daoge_data(force=force_refresh)
except Exception as exc:
    web3daoge_payload = {"records": [], "meta": {"record_count": 0}}
    st.warning(f"Web3Daoge 板块拉取失败：{exc}")

records = payload.get("records", [])
df = pd.DataFrame(records)
if df.empty:
    st.warning("当前无数据。")
    st.stop()

for col in ["tvl_usd", "deposit_apy_pct", "borrow_apy_pct"]:
    df[col] = pd.to_numeric(df.get(col), errors="coerce")

# 北京时间
generated_at_utc = pd.to_datetime(payload.get("generated_at_utc"), utc=True, errors="coerce")
if pd.notna(generated_at_utc):
    generated_at_bj = generated_at_utc.tz_convert(BJ_TZ).strftime("%Y-%m-%d %H:%M:%S")
else:
    generated_at_bj = "-"

connector_status = payload.get("meta", {}).get("connector_status", {})

apy_alert_style = JsCode(
    """
    function(params) {
      if (params.value !== null && params.value !== undefined && Number(params.value) > 8) {
        return {color: '#b91c1c', fontWeight: '700', backgroundColor: '#ffe4e6'};
      }
      return null;
    }
    """
)

link_renderer = JsCode(
    """
    class UrlCellRenderer {
      init(params) {
        this.eGui = document.createElement('a');
        if (!params.value) {
          this.eGui.innerText = '';
          return;
        }
        this.eGui.innerText = '打开链接';
        this.eGui.href = params.value;
        this.eGui.target = '_blank';
        this.eGui.rel = 'noopener noreferrer';
        this.eGui.style.cursor = 'pointer';
        this.eGui.style.color = '#2563eb';
        this.eGui.style.textDecoration = 'none';
        this.eGui.style.fontWeight = '600';
      }
      getGui() { return this.eGui; }
    }
    """
)

grid_css = {
    ".ag-root-wrapper": {"border": "1px solid #dbe7f5", "border-radius": "12px"},
    ".ag-header": {"background-color": "#f7fafc", "border-bottom": "1px solid #dbe7f5"},
    ".ag-header-cell-label": {"font-weight": "700", "color": "#334155"},
    ".ag-row": {"transition": "all 0.18s ease"},
    ".ag-row-hover": {"background-color": "#eef6ff !important"},
    ".ag-cell": {"border-color": "#edf2f7"},
}
tab_web3daoge, tab_stable = st.tabs(["Web3Daoge 实时活动", "稳定币收益表"])

with tab_web3daoge:
    daoge_records = web3daoge_payload.get("records", [])
    daoge_df = pd.DataFrame(daoge_records)
    if daoge_df.empty:
        st.info("Web3Daoge 暂无可展示数据。")
    else:
        if "年化（APY）" not in daoge_df.columns:
            daoge_df["年化（APY）"] = ""
        if "教程链接" not in daoge_df.columns:
            daoge_df["教程链接"] = ""
        daoge_df["教程链接"] = daoge_df["教程链接"].fillna("")
        daoge_df["apy_sort"] = daoge_df["年化（APY）"].map(parse_apy_value)

        daoge_table_df = daoge_df[
            [
                "平台",
                "币种",
                "年化（APY）",
                "单个账户限额",
                "开始时间",
                "结束时间",
                "是否锁仓",
                "派息时间",
                "教程链接",
                "apy_sort",
            ]
        ].copy()
        daoge_table_df = daoge_table_df.sort_values(by="apy_sort", ascending=False, na_position="last")
        daoge_table_df = daoge_table_df.drop(columns=["apy_sort"])

        daoge_gb = GridOptionsBuilder.from_dataframe(daoge_table_df)
        daoge_gb.configure_default_column(filter=True, sortable=True, resizable=True)
        daoge_gb.configure_grid_options(
            suppressRowClickSelection=True,
            rowSelection="single",
            alwaysShowHorizontalScroll=True,
        )
        daoge_gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=20)
        daoge_gb.configure_column("年化（APY）", sort="desc")
        daoge_gb.configure_column("教程链接", cellRenderer=link_renderer)

        AgGrid(
            daoge_table_df,
            gridOptions=daoge_gb.build(),
            allow_unsafe_jscode=True,
            fit_columns_on_grid_load=False,
            enable_enterprise_modules=False,
            height=700,
            custom_css=grid_css,
        )

with tab_stable:
    f1, f2, _ = st.columns([2.4, 2.5, 1.1])
    with f1:
        min_tvl_m = st.number_input(
            "TVL 最低值（百万美元）",
            min_value=0,
            max_value=10_000,
            value=10,
            step=10,
            help="默认 10 = 1000 万美元",
        )

    with f2:
        min_apy = st.number_input(
            "存款 APY 最低值（%）",
            min_value=0.0,
            max_value=1000.0,
            value=5.0,
            step=0.5,
            help="默认 5%",
        )

    filter_mode = st.radio(
        "默认筛选逻辑",
        options=[
            "满足任一（TVL>=1000万 或 APY>=5%）",
            "同时满足（TVL>=1000万 且 APY>=5%）",
        ],
        horizontal=True,
        index=0,
    )

    min_tvl_usd = float(min_tvl_m) * 1_000_000
    tvl_cond = df["tvl_usd"].fillna(0) >= min_tvl_usd
    apy_cond = df["deposit_apy_pct"].fillna(-1) >= float(min_apy)

    if filter_mode.startswith("满足任一"):
        view_df = df[tvl_cond | apy_cond].copy()
    else:
        view_df = df[tvl_cond & apy_cond].copy()

    all_sources = sorted([s for s in view_df["source"].dropna().unique().tolist()])
    selected_sources = st.multiselect("来源筛选", options=all_sources, default=all_sources)
    if selected_sources:
        view_df = view_df[view_df["source"].isin(selected_sources)].copy()

    view_df = view_df.sort_values(by="deposit_apy_pct", ascending=False, na_position="last")
    if view_df.empty:
        st.warning("筛选后无数据，请降低 TVL/APY 阈值。")
    else:
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(
                f'<div class="kpi-card"><div class="kpi-title">记录数</div><div class="kpi-val">{len(view_df)}</div></div>',
                unsafe_allow_html=True,
            )
        with k2:
            st.markdown(
                f'<div class="kpi-card"><div class="kpi-title">来源数</div><div class="kpi-val">{view_df["source"].nunique()}</div></div>',
                unsafe_allow_html=True,
            )
        with k3:
            usdt_cnt = int((view_df["symbol"] == "USDT").sum())
            st.markdown(
                f'<div class="kpi-card"><div class="kpi-title">USDT 条目</div><div class="kpi-val">{usdt_cnt}</div></div>',
                unsafe_allow_html=True,
            )
        with k4:
            usdc_cnt = int((view_df["symbol"] == "USDC").sum())
            st.markdown(
                f'<div class="kpi-card"><div class="kpi-title">USDC 条目</div><div class="kpi-val">{usdc_cnt}</div></div>',
                unsafe_allow_html=True,
            )

        source_counts = view_df["source"].value_counts().to_dict()
        st.markdown(
            '<div class="panel">当前来源条数: '
            + " | ".join([f"{k}: {v}" for k, v in source_counts.items()])
            + "</div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="panel">'
            f'数据生成时间（北京时间）: {generated_at_bj} | 前端自动刷新: 1分钟 | 后端缓存: 5分钟'
            "</div>",
            unsafe_allow_html=True,
        )
        if connector_status:
            st.markdown(
                '<div class="panel">外部连接器状态: '
                + " | ".join([f"{k}: {v}" for k, v in connector_status.items()])
                + "</div>",
                unsafe_allow_html=True,
            )

        view_df["链接"] = view_df["token_entry_url"].fillna("")

        table_df = view_df[
            [
                "source",
                "chain",
                "symbol",
                "deposit_apy_pct",
                "borrow_apy_pct",
                "tvl_usd",
                "链接",
            ]
        ].copy()

        table_df = table_df.rename(
            columns={
                "source": "来源",
                "chain": "链",
                "symbol": "币种",
                "deposit_apy_pct": "存款 APY",
                "borrow_apy_pct": "借款 APY",
                "tvl_usd": "TVL",
            }
        )

        gb = GridOptionsBuilder.from_dataframe(table_df)
        gb.configure_default_column(filter=True, sortable=True, resizable=True)
        gb.configure_grid_options(
            suppressRowClickSelection=True,
            rowSelection="single",
            alwaysShowHorizontalScroll=True,
        )
        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=40)
        gb.configure_column("存款 APY", sort="desc")
        gb.configure_column("TVL", type=["numericColumn"], valueFormatter="x.toLocaleString()")
        for apy_col in ["存款 APY", "借款 APY"]:
            gb.configure_column(
                apy_col,
                type=["numericColumn"],
                valueFormatter="value === null || value === undefined ? '' : value.toFixed(2) + '%'",
                cellStyle=apy_alert_style if apy_col == "存款 APY" else None,
            )
        gb.configure_column("链接", cellRenderer=link_renderer)

        st.subheader("稳定币收益表")
        AgGrid(
            table_df,
            gridOptions=gb.build(),
            allow_unsafe_jscode=True,
            fit_columns_on_grid_load=False,
            enable_enterprise_modules=False,
            height=920,
            custom_css=grid_css,
        )

st.caption(f"页面渲染时间（北京时间）: {datetime.now(BJ_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
st.markdown("</div>", unsafe_allow_html=True)
