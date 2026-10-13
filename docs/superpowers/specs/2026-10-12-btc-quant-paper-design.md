# BTC 量化紙上交易系統 — 設計規格

日期：2026-10-12
依據：`docs/btc-trend-research-2026-10-12.md`（B 方案：趨勢組合 + 4H 逐倉合約）

## 1. 目標與範圍

**目標**：在 production 以紙上交易的方式執行 B 方案 2–3 個月，驗證實盤和回測是否一致，作為之後真實下單的依據。

**包含**：
- 訊號計算
- 紙上帳戶
- 背景執行迴圈
- Postgres 儲存
- Telegram 通知
- 唯讀 API
- 回測與一致性測試

**不包含**：
- 真實下單
- 前端頁面
- 修改現有策略
- 放大倍數設定（固定 1 倍）

## 2. 策略規則（和研究腳本逐項一致）

### 2.1 趨勢部位（現貨）
- 資料：BingX `BTC/USDT:USDT` 日線，UTC 時間。
- 第 t 日收盤後計算 12 個訊號，各為 0 或 1，取平均得到 `ens`：
  - 唐奇安狀態機 (n, m)：(20,10)、(55,20)、(100,50)、(55,10)、(100,20)。
    空手時，若收盤價 > 前 n 日最高價，轉為持有；持有時，若收盤價 < 前 m 日最低價，轉為空手。
  - 時間序列動能：`close / close.shift(L) - 1 > 0`，L = 30、90、180。
  - 均線：`close > SMA(L)`，L = 50、100、200。
- 目標曝險 `target = clip(ens × 0.40 / vol30, 上限 0.90)`，
  其中 `vol30 = std(日報酬, 30) × √365`。
  - 研究版本的上限是 1.0。這裡改成 **0.90**，保留至少 10% 的 USDT 作為合約保證金（理由見 §2.3）。
- 執行：每日 UTC 00:00 後第一次迴圈，以當時價格把現貨部位調整到 `target × equity`。
  成本是調整金額 × 0.1%。現貨不計資金費。

### 2.2 4H 逐倉合約部位
- 資料：BingX `BTC/USDT:USDT` 4H K 棒。
  - ATR14 = TR 的 14 根簡單平均
  - `up20` / `dn20` = 前 20 根的最高價 / 最低價（不含當根）
- 市況濾網：4H K 棒所在日期 D，使用 D−1 日收盤的 `ens`。
- 進場訊號（第 j 根收盤時判斷，第 j+1 根開盤進場）：
  - 做多：`close > up20` 且 `ens ≥ 0.5`
  - 做空：`close < dn20` 且 `ens == 0`
- 同時最多只持有 1 筆。
- 部位計算：
  - `stop_pct = 1.5 × ATR / entry`
  - `lev = min(25, floor(1 / (2 × stop_pct + 0.005)))`；`lev < 1` 就不進場
  - `notional = equity × 0.02 / stop_pct`
  - `margin = notional / lev`（逐倉）
  - 停損 = `entry × (1 ∓ stop_pct)`
  - 停利 = `entry × (1 ± 2 × stop_pct)`
  - 強平價 = `entry × (1 ∓ (1/lev − 0.005))`
- 出場（紙上帳戶每次迴圈檢查最新成交價）：
  - 價格**連續移動**越過停損（K 棒內部，或距離上次報價不到 15 分鐘）：視同交易所停損單，以停損價成交
  - 價格**跳空**越過停損（新 K 棒開盤，或報價中斷超過 15 分鐘）：以停損價與觀察價中較差者成交
  - 跳空越過強平價：損失 = margin，該筆結束
  - （2026-10-13 修訂：原本一律用較差價成交，會讓回測以整根 K 棒的最低點成交，高估虧損）
  - 價格達到停利：以停利價成交
  - 同一次檢查同時符合停損和停利：視為停損
- 成本：
  - 手續費每邊 0.05%
  - 資金費每 8 小時依 BingX 實際費率計算，`notional × rate`；做多付正費率，做空收正費率

### 2.3 共用本金
- `equity = USDT 現金 + 現貨 BTC 市值 + 合約未實現損益`
- 合約保證金中位數約為 equity 的 4.6%，最高約 10%，所以現貨上限設為 0.90。
- 調整現貨時若 USDT 不足以支應持倉中的保證金，就少買，優先保留保證金。

## 3. 架構

```
btc_quant/
  __init__.py
  signals.py   純函式：daily_ensemble(df_1d)、trend_target(df_1d)、tactical_signal(df_4h, ens)、size_position(...)
  paper.py     PaperAccount：狀態（現金、現貨、合約部位、峰值）、rebalance()、open()、on_price()、accrue_funding()、to_dict()/from_dict()
  store.py     load_state()/save_state()/append_event()：有 DATABASE_URL 用 Postgres，否則用 logs/btc_quant_state.json
  runner.py    async run_btc_quant_loop()：每 300 秒一次；job lease "btc_quant"；抓 1d(400)/4h(100)/ticker/funding
  backtest.py  用 signals.py 的同一組函式，對歷史 K 棒逐根模擬
```

整合到 `main.py`（盡量少改）：
- `start_background_tasks` 在 `BTC_QUANT_ENABLED=true` 時加入這個迴圈
- `BACKGROUND_JOB_LABELS` 加入 `"btc_quant_loop": "BTC 量化（紙上）"`
- 新增 `GET /api/btc-quant/status`

## 4. 資料流（runner 每次迴圈）
1. 嘗試取得 job lease，失敗就跳過這次。
2. 抓 ticker，執行 `paper.on_price(last)`：檢查停損 / 停利 / 強平，有出場就記錄並發 Telegram。
3. 跨過 8 小時資金費結算點：`accrue_funding(rate)`。
4. 日期改變（UTC）：抓日線，`trend_target` → `rebalance`，記錄並發 Telegram，再發一份每日摘要。
5. 有新的 4H K 棒收盤：抓 4H 資料，沒有持倉時呼叫 `tactical_signal`，有訊號就 `open()`，記錄並發 Telegram。
6. `save_state()`，並更新 data source health。

## 5. 儲存（Postgres migration 2）
```sql
CREATE TABLE IF NOT EXISTS btc_quant_state (
  id TEXT PRIMARY KEY, state JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS btc_quant_events (
  id BIGSERIAL PRIMARY KEY, ts TIMESTAMPTZ NOT NULL DEFAULT now(), kind TEXT NOT NULL, payload JSONB NOT NULL);
CREATE INDEX IF NOT EXISTS idx_btc_quant_events_ts ON btc_quant_events (ts);
```
- 事件 `kind` 包含：`rebalance`、`open`、`close`、`funding`、`daily_equity`、`error`。
- 狀態中記錄 `last_daily_date`、`last_4h_bar_ts`、`last_funding_ts`，重啟後不會重複處理。

## 6. 設定（環境變數）
| 變數 | 預設 | 說明 |
|---|---|---|
| `BTC_QUANT_ENABLED` | `false` | 開關 |
| `BTC_QUANT_PAPER_EQUITY` | `10000` | 紙上起始本金（USDT），只在第一次初始化時使用 |

## 7. 錯誤處理
- 行情抓取失敗：這次跳過，連續 3 次失敗發 Telegram 警告（沿用 `LOOP_FAILURE_ALERT_THRESHOLD`）。
- 行情超過 30 分鐘沒更新：不開新倉，已有持倉照常檢查停損。
- 淨值回撤超過 30%：發 Telegram 警告，但不自動停止（回測的最大回撤是 −44%）。

## 8. API
`GET /api/btc-quant/status` 回傳：
- `enabled`、`start_equity`、`equity`、`return_pct`、`max_drawdown_pct`
- `trend: {target, btc_qty, value}`
- `tactical: {position | null}`
- `recent_events`（最近 50 筆）

## 9. 測試
- `test_btc_quant_signals.py`：
  - 唐奇安狀態機、動能、均線、`ens` 範圍
  - `trend_target` 的 0.90 上限
  - `tactical_signal` 的多 / 空 / 無訊號
  - `size_position` 的槓桿上限 25、強平距離 ≥ 2 × 停損、`lev < 1` 時不進場
- `test_btc_quant_paper.py`：
  - 停損、停利、同時觸發算停損
  - 跳空越過停損時以較差價成交；跳空越過強平價時損失 = margin
  - 資金費方向；`rebalance` 會保留保證金
  - 狀態序列化後再還原，結果相同
- `test_btc_quant_parity.py`：同一段歷史 K 棒，`backtest.py` 和逐根餵給 `PaperAccount` 的 runner 邏輯，必須產生**相同的進場時間和方向**。
- `test_btc_quant_runner.py`：用假的 exchange，驗證日期切換只調倉一次、新 4H K 棒只判斷一次、重啟後不重複處理。

## 10. 紙上交易階段的成功標準（3 個月）
- 每根 4H K 棒和每天的調倉都有紀錄，沒有遺漏。
- 用同期的 BingX 資料重跑 `backtest.py`，進場時間和方向完全一致，損益差距只來自成交價差。
- 結束後產出一份實盤 vs 回測報告，再決定要不要做真實下單。
