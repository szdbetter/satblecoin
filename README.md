# 稳定币收益实时对比仪表盘

## 目标
对比全网 USDT/USDC 的稳定币收益，覆盖：
- Aave
- Morpho
- Solana 主流（Kamino、MarginFi）
- DeFiLlama 精选（TVL >= 1000 万美金）
- OKX 钱包理财活动（Simple Earn / Onchain Earn）
- Binance 理财（Simple Earn，需 API Key）

## 特性
- Python 后端（FastAPI）
- Web 仪表盘（Streamlit）
- 可筛选/排序/分页表格（AgGrid）
- 图表分析（Plotly）
- 自动刷新：前端每 1 分钟；后端缓存 5 分钟
- 页面打开即拉取；支持手动强制刷新

## 快速启动
```bash
cd /Users/kimi/Desktop/Jimmy/Python/Web3/工作室脚本/项目/查找稳定币收益
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

启动后端：
```bash
uvicorn backend.api:app --host 0.0.0.0 --port 8000 --reload
```

另开一个终端启动前端：
```bash
streamlit run frontend/app.py --server.port 8501
```

打开：`http://localhost:8501`

也可直接使用脚本：
```bash
./start_backend.sh
./start_frontend.sh
```

## API
- `GET /api/health`
- `GET /api/yields?force_refresh=true|false`

## 数据口径
- 展示 `USDT`、`USDC`、`PYUSD`、`USDG`
- 若协议含借贷：同时展示存款和借贷利率
- 若仅存款：借贷列为空
- 入口链接：优先协议入口，无法精确构造时回退到 DeFiLlama 池页面

## Binance 接入（可选）
Binance 官方 Simple Earn 接口需要签名认证。若需要启用，先设置：
```bash
export BINANCE_API_KEY='你的key'
export BINANCE_API_SECRET='你的secret'
```
然后重启后端。未配置时系统会自动跳过 Binance 数据，不影响其他来源。

## OKX 接入（可选，默认关闭）
因 OKX 会按地区限制展示产品页，默认关闭 OKX 数据源，避免出现“当前地区不可用”条目。
如需开启：
```bash
export ENABLE_OKX=1
```
然后重启后端。

## Binance Web3 钱包（免费无 Key）
- 已内置公开接入源：`Binance Web3钱包-公开`
- 数据方式：通过公开 DeFi 数据（无需 API Key）聚合 Binance Web3 常见稳定币池（Venus / Lista / Morpho）
- 说明：
  - `Binance理财(Simple Earn)` 仍是官方 `USER_DATA` 接口，需 `API Key + Secret`
  - 若不配置 Key，系统会自动显示 `disabled:requires_api_key(USER_DATA)`，但不影响 `Binance Web3钱包-公开`

## Web3Daoge 独立版块
- 新增后端接口：`GET /api/web3daoge?force_refresh=true|false`
- 数据源：`https://web3daoge.com/data.json`
- 前端新增独立表格版块：`Web3Daoge 实时活动（独立版块）`
- 字段按原站格式展示，并补齐相对教程链接为绝对链接。
- `Web3Daoge` 缓存更新周期：默认 `5` 分钟（可通过 `WEB3DAOGE_CACHE_TTL_SECONDS` 调整）
