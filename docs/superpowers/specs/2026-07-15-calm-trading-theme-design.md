# 「不高壓交易」視覺重設計 — Sand & Sage 主題

**日期：** 2026-07-15
**範圍：** `crypto-trading-dashboard`（Next.js 前端），全站套用
**狀態：** 已與使用者確認方向，待寫實作計畫

## 背景與動機

現有前端是標準 shadcn 深色儀表板：近黑背景（`oklch(0.16 264)`）、灰階卡片、綠/紅語意色。功能完整但視覺上「沒有感覺」，且多處細節（呼吸燈脈動、跑馬燈快訊、警示三角圖示）在無意識中放大「盯盤緊張感」。

使用者明確表達的目標：**交易本身已經是高壓的事，介面不應該加重這種壓力**。因此這次重設計以「降壓」為第一原則，同時透過色彩心理學（低飽和、高明度、暖色調）達成，但不犧牲技術圖表的專業可信度。

過程中透過視覺協作面板比較了三個方向（霓虹終端 / 編輯感數據藝術 / 極光玻璃）與三個簡約變體，使用者最終在淺色暖調系列中選定 **Sand & Sage**，並要求技術圖表維持業界標準配色不套用暖色系。

## 設計原則

1. **UI 外殼走暖色降壓路線，技術圖表維持專業標準色** — 兩者是刻意的區隔，不是遺漏。使用者本人明確要求：K 線/技術指標圖表要靠業界慣例（紅跌綠漲）維持專業使用者的信任，只有「介面外殼」（背景、卡片、徽章、按鈕、動效）走 Sand & Sage。
2. **降低視覺急迫感** — 呼吸燈、跑馬燈、警示圖示這類「有急事發生」的視覺語言，改成穩定、緩慢、安靜的版本。
3. **語意色仍需可辨識** — 多/空、賺/賠的顏色區分不能模糊掉，只是從「警報級飽和度」降到「柔和但清楚」。
4. **深色模式不是回到原本的純黑** — 深色選項要跟淺色版同一套「暖、柔」的設計邏輯，只是換成暗背景，不是走回使用者本來就嫌棄的那種黑。

## 色彩系統

### 淺色預設：Sand & Sage

UI 外殼（背景、卡片、邊框、徽章、按鈕）使用的語意色 token（沿用 `globals.css` 現有的 `--long` / `--short` / `--background` / `--card` 等變數名稱，改變數值，格式在實作時換算成 OKLCH 以符合現有慣例）：

| Token | 用途 | 起始值 (hex，實作時換算 OKLCH) |
|---|---|---|
| `--background` | 頁面底色 | `#ece6db`（暖沙色） |
| `--card` | 卡片底色 | `#f7f3ea` |
| `--foreground` | 主要文字 | `#3d3527`（暖炭色，非純黑） |
| `--muted-foreground` | 次要文字 | `#8c8272` |
| `--border` | 邊框 | `rgba(70,60,45,0.08)` |
| `--long` | 多／賺語意色（UI 徽章、文字、按鈕） | `#5c6e4f`（鼠尾草綠，柔和） |
| `--short` | 空／賠語意色（UI 徽章、文字、按鈕） | `#a86f6f`（乾燥玫瑰粉，柔和） |

### 深色選項：暖炭灰（Warm Charcoal）

同一套語意邏輯，重新校正到暗背景：暖灰黑（非純黑，帶一點炭色/棕色調），`--long`/`--short` 用同樣柔和的鼠尾草綠/玫瑰粉但提高明度以在暗底可讀。實作時需另外定義一組 `.dark` 或等效的 CSS 變數集合，並在 header 加入主題切換 UI（目前 `layout.tsx` 沒有任何主題切換機制，需新增）。

### 例外：技術圖表維持業界標準色

以下元件是「數據視覺化本身」，維持標準高飽和紅綠（漲=綠、跌=紅），**不套用 Sand & Sage 的柔和色**：

- `signal-chart.tsx`（K 線圖）
- `gex-wall-chart.tsx`（GEX 曝險牆）
- `liquidation-heatmap-chart.tsx`（清算熱力圖）
- `rsi2-technical-chart.tsx`（RSI2 技術圖）
- `price-range-gauge.tsx`（價格區間量表——本質是技術讀數，非狀態徽章）

實作方式：新增一組獨立的「圖表專用」色彩 token `--chart-bull` / `--chart-bear`（維持目前 `--chart-1`/`--chart-2` 的原始高飽和數值），跟 UI 語意色 `--long`/`--short` 脫鉤——現況 `--chart-1`/`--chart-2` 其實只是 `--long`/`--short` 的重複值，這次順便拆開。`--chart-3`～`--chart-5`（多系列圖表用的中性灰階）不受影響。上述五個元件改用 `--chart-bull`/`--chart-bear`；其餘所有使用 `--long`/`--short`（`text-long`、`bg-long`、`border-long` 等 Tailwind class）的元件——包括 `hero-signal.tsx`、`price-levels.tsx`、`symbol-watchlist.tsx`、`opportunity-list.tsx`、`monitoring-panel.tsx`、`us-stock-*.tsx`、`recent-history.tsx`、`meme-*.tsx`、`squeeze-feed.tsx`、`news-radar.tsx`、`options-analytics-panel.tsx`、`backtest-sandbox-panel.tsx`、`high-winrate-panel.tsx`、`confluence-badge.tsx`、`favorites-overview.tsx`、`watchlist-editor.tsx`、`whale-sweep-stream.tsx`、`copy-value.tsx`——維持用 `--long`/`--short`，只是這兩個 token 本身的數值換成柔和版。

這個切分是本次設計唯一的「顏色分流點」，實作計畫需要把它列為明確驗收項目，避免技術圖表被誤套用暖色。

## 降壓的動態細節

| 現況 | 改為 | 檔案 |
|---|---|---|
| Chatbot 收合按鈕呼吸燈脈動（`animate-chatbot-breathe`，box-shadow 放大縮小） | 穩定柔光暈，無脈動動畫 | `globals.css`（移除 keyframes 或改為靜態陰影）、`trading-chatbot.tsx` |
| AI 副官快訊跑馬燈橫向捲動（`animate-broadcast-marquee`） | 緩慢淡入淡出輪播（crossfade），不橫向掃動 | `globals.css`、`trading-chatbot.tsx` |
| 連線狀態燈號 | 已經是常亮，不需更動——只需確認新色調下對比度足夠 | `trade-dashboard.tsx` header 狀態 pill |
| 錯誤/免責聲明區塊的 `AlertTriangle` 警示三角圖示 | 移除圖示，用文字字重/留白傳達即可，色調也降飽和 | `trade-dashboard.tsx` footer、各分頁的紅色錯誤橫幅 |
| `gex-spot-pulse` 呼吸脈衝（GEX 圖表現貨價發光線） | **保留**——這個屬於技術圖表範疇（例外清單內），維持原本的專業呈現邏輯，不算「高壓」動效 | `globals.css`、`gex-wall-chart.tsx` |

## 範圍與 Rollout

- 全站套用，非單一頁面試點：所有 `components/*.tsx`（除上述五個技術圖表例外）與 `app/globals.css` 的色彩系統都要換成 Sand & Sage 邏輯。
- 新增深色（暖炭灰）主題切換：`layout.tsx` 目前寫死 `colorScheme: 'dark'`，需要改為可切換，並加入切換 UI（放在 header，靠近現有的連線狀態 pill）。
- Typography（Inter + JetBrains Mono）不變，字體選擇本身跟「高壓感」無關，不在本次範圍內。

## 不在範圍內

- 不重新設計資訊架構（分頁分類、元件擺放順序維持現狀，這是上一輪顧問備忘錄才剛做過的事）。
- 不更動圖表函式庫或技術指標運算邏輯，僅調整技術圖表的配色 token 來源。
- 不新增後端 API 或資料欄位。
