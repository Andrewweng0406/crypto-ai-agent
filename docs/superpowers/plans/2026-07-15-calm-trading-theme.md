# Calm Trading Theme (Sand & Sage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the crypto-trading-dashboard's stark black theme with a warm, low-arousal "Sand & Sage" light theme (plus a "Warm Charcoal" dark companion), while keeping all technical price charts on standard high-saturation red/green so they stay professionally credible.

**Architecture:** All UI chrome (backgrounds, cards, badges, buttons, banners) reads color from the existing `--long`/`--short`/`--background`/`--card`/etc. CSS custom properties in `app/globals.css` — only the *values* change, not the class names components already use. Actual price-action charts (candlesticks, GEX walls, liquidation heatmap, RSI2 chart, price-range gauge) currently reuse `--long`/`--short` too; this plan splits them onto new, theme-invariant `--chart-bull`/`--chart-bear` tokens so redesigning the UI palette can never accidentally recolor a K-line. A new `.dark` class (toggled by a small client-side theme switcher, persisted to `localStorage`) carries the Warm Charcoal companion values; Tailwind's `dark:` variant already resolves off `.dark` via the existing `@custom-variant dark (&:is(.dark *))` rule, so no component markup needs a `dark:` prefix added for the base palette to work.

**Tech Stack:** Next.js 16 (App Router) + React 19, Tailwind CSS v4 (`@theme inline`), shadcn primitives, lucide-react icons, tw-animate-css (already a dependency, used for the new fade-in ticker). No frontend test runner exists in this project (`package.json` has no jest/vitest/playwright) — verification for every task is `npm run build` (type-checks + compiles Tailwind) plus explicit `grep` checks and a final manual QA pass, not unit tests.

## Global Constraints

- Spec source of truth: `docs/superpowers/specs/2026-07-15-calm-trading-theme-design.md` — every color value below is copied from its token table / the approved artifact preview.
- The five chart components (`signal-chart.tsx`, `gex-wall-chart.tsx`, `liquidation-heatmap-chart.tsx`, `rsi2-technical-chart.tsx`, `price-range-gauge.tsx`) must end up using **zero** `--long`/`--short`-derived classes — they are the one part of the app that does *not* follow the calm palette.
- `--chart-bull` / `--chart-bear` must be defined once and must NOT be redefined inside `.dark` — they stay identical in both themes (this is what "professional standard color, independent of theme" means concretely).
- No new npm dependency may be added for the theme toggle or the ticker fade — `tw-animate-css` (already installed) and a ~15-line hand-rolled localStorage helper cover both needs.
- Every task must leave `npm run build` passing before it is committed.

---

### Task 1: Sand & Sage / Warm Charcoal color tokens

**Files:**
- Modify: `crypto-trading-dashboard/app/globals.css:54-97` (the `:root:root { ... }` color block)
- Modify: `crypto-trading-dashboard/app/globals.css:7-52` (the `@theme inline { ... }` token registration block)

**Interfaces:**
- Produces: CSS custom properties `--background`, `--foreground`, `--card`, `--card-foreground`, `--popover`, `--popover-foreground`, `--primary`, `--primary-foreground`, `--secondary`, `--secondary-foreground`, `--muted`, `--muted-foreground`, `--accent`, `--accent-foreground`, `--destructive`, `--border`, `--input`, `--ring`, `--long`, `--long-foreground`, `--short`, `--short-foreground`, `--chart-1`..`--chart-5`, `--sidebar*` (light values on `:root:root`, dark values on `.dark`) — every later task and every existing component reads these by name, none of the names change.
- Produces (new): `--chart-bull`, `--chart-bull-foreground`, `--chart-bear`, `--chart-bear-foreground` (theme-invariant, defined once) and their Tailwind utility registrations `--color-chart-bull`, `--color-chart-bull-foreground`, `--color-chart-bear`, `--color-chart-bear-foreground` in `@theme inline` — Task 4 consumes these as `text-chart-bull`, `bg-chart-bull`, `border-chart-bull`, `fill-chart-bull`, `stroke-chart-bull`, `from-chart-bull`, `via-chart-bull`, `to-chart-bull` (and the `-bear`/`-foreground` equivalents).

- [ ] **Step 1: Replace the `@theme inline` block to register the two new chart tokens**

In `crypto-trading-dashboard/app/globals.css`, find the `@theme inline { ... }` block (lines 7-52) and add four lines right after `--color-short-foreground: var(--short-foreground);` (currently line 13):

```css
  --color-short-foreground: var(--short-foreground);
  --color-chart-bull: var(--chart-bull);
  --color-chart-bull-foreground: var(--chart-bull-foreground);
  --color-chart-bear: var(--chart-bear);
  --color-chart-bear-foreground: var(--chart-bear-foreground);
```

- [ ] **Step 2: Replace the color value block with Sand & Sage (light) + chart tokens**

Replace the entire `:root:root { ... }` block (lines 54-97 in the original file) with:

```css
:root:root {
  color-scheme: light;
  --background: #ece6db;
  --foreground: #3d3527;
  --card: #f7f3ea;
  --card-foreground: #3d3527;
  --popover: #fffdf8;
  --popover-foreground: #3d3527;
  --primary: #4a4030;
  --primary-foreground: #f7f3ea;
  --secondary: #e2dccc;
  --secondary-foreground: #3d3527;
  --muted: #e2dccc;
  --muted-foreground: #8c8272;
  --accent: #e2dccc;
  --accent-foreground: #3d3527;
  --destructive: #a3685f;
  --border: rgba(70, 60, 45, 0.08);
  --input: rgba(70, 60, 45, 0.14);
  --ring: #4a4030;
  --long: #5c6e4f;
  --long-foreground: #f7f3ea;
  --short: #a3685f;
  --short-foreground: #f7f3ea;
  --chart-1: #5c6e4f;
  --chart-2: #a3685f;
  --chart-3: #8c8272;
  --chart-4: #b3a890;
  --chart-5: #d9d0bf;
  --radius: 0.75rem;
  --sidebar: #f2ede2;
  --sidebar-foreground: #3d3527;
  --sidebar-primary: #4a4030;
  --sidebar-primary-foreground: #f7f3ea;
  --sidebar-accent: #e2dccc;
  --sidebar-accent-foreground: #3d3527;
  --sidebar-border: rgba(70, 60, 45, 0.08);
  --sidebar-ring: #4a4030;

  /* 2026-07-15 降壓改版：K線/GEX/清算牆/RSI2/區間量表這五個「技術圖表」
     元件維持業界標準紅漲綠跌，不跟著 Sand & Sage 暖色系走，也不隨深淺色
     模式切換而改變（.dark 不重新定義這兩個 token）——見設計規格文件。 */
  --chart-bull: #1f9d55;
  --chart-bull-foreground: #ffffff;
  --chart-bear: #d1453d;
  --chart-bear-foreground: #ffffff;
}

.dark {
  color-scheme: dark;
  --background: #1b1712;
  --foreground: #f0e9db;
  --card: #251f18;
  --card-foreground: #f0e9db;
  --popover: #2b241c;
  --popover-foreground: #f0e9db;
  --primary: #f0e9db;
  --primary-foreground: #1b1712;
  --secondary: #322a20;
  --secondary-foreground: #f0e9db;
  --muted: #2b241c;
  --muted-foreground: #a89a85;
  --accent: #322a20;
  --accent-foreground: #f0e9db;
  --destructive: #d19a91;
  --border: rgba(240, 233, 219, 0.09);
  --input: rgba(240, 233, 219, 0.12);
  --ring: #f0e9db;
  --long: #93b17e;
  --long-foreground: #1b1712;
  --short: #d19a91;
  --short-foreground: #1b1712;
  --chart-1: #93b17e;
  --chart-2: #d19a91;
  --chart-3: #a89a85;
  --chart-4: #7d715d;
  --chart-5: #322a20;
  --sidebar: #211b15;
  --sidebar-foreground: #f0e9db;
  --sidebar-primary: #f0e9db;
  --sidebar-primary-foreground: #1b1712;
  --sidebar-accent: #322a20;
  --sidebar-accent-foreground: #f0e9db;
  --sidebar-border: rgba(240, 233, 219, 0.09);
  --sidebar-ring: #f0e9db;
}
```

Note: `--chart-bull`/`--chart-bear` are declared only once, on `:root:root`, and deliberately absent from `.dark` — that's what keeps chart colors identical across themes.

- [ ] **Step 3: Verify the build compiles**

Run: `cd crypto-trading-dashboard && npm run build`
Expected: build succeeds with no Tailwind/type errors (unused old dark-only oklch values are simply gone; nothing referenced them by name that isn't still defined).

- [ ] **Step 4: Verify no leftover dark-only oklch color-scheme lock remains**

Run: `grep -n "color-scheme: dark;" crypto-trading-dashboard/app/globals.css`
Expected: one match, inside the new `.dark { ... }` block only (not on `:root:root`).

- [ ] **Step 5: Commit**

```bash
cd crypto-trading-dashboard
git add app/globals.css
git commit -m "Add Sand & Sage light theme + Warm Charcoal dark companion, split chart colors from UI semantic colors"
```

---

### Task 2: Light/dark theme toggle

**Files:**
- Create: `crypto-trading-dashboard/lib/theme.ts`
- Create: `crypto-trading-dashboard/components/theme-toggle.tsx`
- Modify: `crypto-trading-dashboard/app/layout.tsx`
- Modify: `crypto-trading-dashboard/components/trade-dashboard.tsx:474-492` (header)

**Interfaces:**
- Consumes: `.dark` class contract from Task 1 (toggling this class on `<html>` is what switches themes).
- Produces: `THEME_STORAGE_KEY: string`, `type Theme = "light" | "dark"`, `getSystemTheme(): Theme`, `applyTheme(theme: Theme): void` from `lib/theme.ts` — consumed by `components/theme-toggle.tsx` and by the inline blocking script in `layout.tsx` (which duplicates the storage key as a literal string since it runs before any JS module loads — see Step 2).
- Produces: `<ThemeToggle />` component (no props) — rendered inside `trade-dashboard.tsx`'s header.

- [ ] **Step 1: Create the theme helper module**

Create `crypto-trading-dashboard/lib/theme.ts`:

```ts
export const THEME_STORAGE_KEY = "weng-crypto-theme"

export type Theme = "light" | "dark"

export function getSystemTheme(): Theme {
  if (typeof window === "undefined") return "light"
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

export function getActiveTheme(): Theme {
  if (typeof window === "undefined") return "light"
  return document.documentElement.classList.contains("dark") ? "dark" : "light"
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark")
  window.localStorage.setItem(THEME_STORAGE_KEY, theme)
}
```

- [ ] **Step 2: Add a pre-hydration blocking script and fix the viewport meta in the root layout**

In `crypto-trading-dashboard/app/layout.tsx`, replace the whole file with:

```tsx
import type { Metadata, Viewport } from 'next'
import { Inter, JetBrains_Mono } from 'next/font/google'
import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
})

export const metadata: Metadata = {
  title: 'Weng Crypto — AI Trading Signals',
  description:
    'A premium AI-powered crypto trading signal terminal. Real-time entries, take-profit and stop-loss levels built for active traders.',
  generator: 'v0.app',
}

export const viewport: Viewport = {
  colorScheme: 'light dark',
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#ece6db' },
    { media: '(prefers-color-scheme: dark)', color: '#1b1712' },
  ],
}

// 2026-07-15 降壓改版：這段內嵌 script 必須在 React hydrate 之前、畫面
// 第一次繪製之前就跑完，才不會先閃一下錯誤的主題再跳回正確的（FOUC）。
// 這裡的 'weng-crypto-theme' 字串跟 lib/theme.ts 的 THEME_STORAGE_KEY
// 常數必須手動保持一致——這支 script 不能 import 任何模組。
const themeInitScript = `(function(){try{var s=localStorage.getItem('weng-crypto-theme');var d=s?s==='dark':window.matchMedia('(prefers-color-scheme: dark)').matches;if(d)document.documentElement.classList.add('dark')}catch(e){}})()`

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`bg-background ${inter.variable} ${jetbrainsMono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="font-sans antialiased">{children}</body>
    </html>
  )
}
```

- [ ] **Step 3: Create the toggle button component**

Create `crypto-trading-dashboard/components/theme-toggle.tsx`:

```tsx
"use client"

import { useEffect, useState } from "react"
import { Moon, Sun } from "lucide-react"
import { applyTheme, getActiveTheme, type Theme } from "@/lib/theme"

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light")

  useEffect(() => {
    setTheme(getActiveTheme())
  }, [])

  return (
    <button
      type="button"
      onClick={() => {
        const next: Theme = theme === "dark" ? "light" : "dark"
        applyTheme(next)
        setTheme(next)
      }}
      aria-label={theme === "dark" ? "切換為淺色模式" : "切換為深色模式"}
      className="flex size-8 items-center justify-center rounded-full border border-border/60 bg-card text-muted-foreground transition-colors hover:text-foreground"
    >
      {theme === "dark" ? <Sun className="size-4" aria-hidden="true" /> : <Moon className="size-4" aria-hidden="true" />}
    </button>
  )
}
```

- [ ] **Step 4: Wire the toggle into the dashboard header**

In `crypto-trading-dashboard/components/trade-dashboard.tsx`, add the import near the other component imports (after the `FavoritesOverview` import, line 76):

```tsx
import { FavoritesOverview } from "@/components/favorites-overview"
import { ThemeToggle } from "@/components/theme-toggle"
```

Then in the header (lines 484-491), add the toggle next to the status pill:

```tsx
        <div className="flex items-center gap-2.5">
          <div
            className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs ${
              activeError ? "border-short/40 bg-short/10 text-short" : "border-border/60 bg-card text-muted-foreground"
            }`}
          >
            <Activity className={`size-3.5 ${isConnected ? "text-long" : ""}`} aria-hidden="true" />
            {statusLabel}
          </div>
          <ThemeToggle />
        </div>
```

This replaces the original bare `<div className={...status pill...}>...</div>` that sat directly under the `<header>` opening tag — it's now wrapped together with `<ThemeToggle />` in a `flex items-center gap-2.5` container so they sit side by side.

- [ ] **Step 5: Verify the build compiles**

Run: `cd crypto-trading-dashboard && npm run build`
Expected: build succeeds, no type errors on the new files.

- [ ] **Step 6: Manual verification**

Run: `cd crypto-trading-dashboard && npm run dev`
Open `http://localhost:3000`, click the new moon/sun button in the header, and confirm the whole page switches between the Sand & Sage and Warm Charcoal palettes instantly, and that reloading the page keeps the chosen theme (persisted via `localStorage`).

- [ ] **Step 7: Commit**

```bash
cd crypto-trading-dashboard
git add lib/theme.ts components/theme-toggle.tsx app/layout.tsx components/trade-dashboard.tsx
git commit -m "Add light/dark theme toggle with localStorage persistence and FOUC-free hydration"
```

---

### Task 3: Soften the AI chatbot's motion

**Files:**
- Modify: `crypto-trading-dashboard/app/globals.css:108-128` (chatbot breathe keyframes) and `:154-174` (broadcast marquee keyframes)
- Modify: `crypto-trading-dashboard/components/trading-chatbot.tsx:134-150` (collapsed button) and `:244-272` (`BroadcastTicker`)

**Interfaces:**
- Consumes: `--primary`, `--primary-foreground` tokens from Task 1 (used for the steady glow ring color).
- Produces: no new exports — this task only changes internal styling/markup of `TradingChatbot`/`BroadcastTicker`, which no other file imports beyond their existing default export.

- [ ] **Step 1: Remove the breathing and marquee keyframes from globals.css, keep the GEX pulse**

In `crypto-trading-dashboard/app/globals.css`, delete these two blocks entirely (lines 108-128 and 154-174 in the original file — the `gex-spot-pulse` block between them, lines 130-152, stays untouched because it belongs to the chart-color exception, not the "calm UI" changes):

```css
/* DELETE this whole block: */
/* 💬 AI 交易軍師助理：收合按鈕的呼吸燈效果 ... */
@keyframes chatbot-breathe {
  0%,
  100% {
    box-shadow: 0 0 0 0 oklch(0.72 0.16 154 / 45%), 0 4px 14px 0 oklch(0.72 0.16 154 / 25%);
  }
  50% {
    box-shadow: 0 0 0 10px oklch(0.72 0.16 154 / 0%), 0 4px 20px 4px oklch(0.72 0.16 154 / 35%);
  }
}

.animate-chatbot-breathe {
  animation: chatbot-breathe 2.8s ease-in-out infinite;
}

@media (prefers-reduced-motion: reduce) {
  .animate-chatbot-breathe {
    animation: none;
  }
}
```

```css
/* DELETE this whole block: */
/* 💬 AI副官戰況跑馬燈：文字從右往左橫向捲動 ... */
@keyframes broadcast-marquee {
  0% {
    transform: translateX(100%);
  }
  100% {
    transform: translateX(-100%);
  }
}

.animate-broadcast-marquee {
  animation: broadcast-marquee 14s linear infinite;
}

@media (prefers-reduced-motion: reduce) {
  .animate-broadcast-marquee {
    animation: none;
    transform: none;
  }
}
```

- [ ] **Step 2: Replace the breathing button with a steady glow**

In `crypto-trading-dashboard/components/trading-chatbot.tsx`, change the collapsed button (around line 137):

```tsx
// Before:
          className="animate-chatbot-breathe fixed bottom-6 right-6 z-50 flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground transition-transform hover:scale-105"

// After:
          className="fixed bottom-6 right-6 z-50 flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-[0_0_0_6px] shadow-primary/15 transition-transform hover:scale-105"
```

- [ ] **Step 3: Replace the horizontal marquee with a calm fade-in**

In `crypto-trading-dashboard/components/trading-chatbot.tsx`, replace the whole `BroadcastTicker` function (lines 247-272) with:

```tsx
// 💬 AI副官0-token戰況通知：緩慢淡入顯示最新一則事件（迷因當沖新訊號/
// 期權大單），點擊直接把這句話送進LLM觸發真正的深度分析（按需計費）。這裡
// 顯示的文字本身完全不消耗API額度，是後端純字串模板組合出來的。key={item.id}
// 讓每次換一則新事件時整個 span 重新掛載，重新觸發一次 fade-in（tw-animate-css
// 提供的 animate-in/fade-in 工具類別），取代原本橫向捲動的跑馬燈。
function BroadcastTicker({
  item,
  disabled,
  onClick,
}: {
  item: AssistantBroadcastItem
  disabled: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title="點擊觸發 AI 深度分析"
      className="flex w-full items-center gap-2 overflow-hidden border-b border-amber-400/30 bg-amber-400/10 px-3 py-1.5 text-left transition-colors hover:bg-amber-400/15 disabled:cursor-not-allowed disabled:opacity-60"
    >
      <Radio className="size-3.5 shrink-0 text-amber-400" aria-hidden="true" />
      <span
        key={item.id}
        className="animate-in fade-in duration-700 flex-1 truncate font-mono text-xs font-semibold text-amber-400"
      >
        {item.message}
      </span>
    </button>
  )
}
```

(The only functional changes: `Radio` no longer has `animate-pulse`; the message `span` lost `relative overflow-hidden whitespace-nowrap` plus the nested `animate-broadcast-marquee` span, gained `key={item.id}` + `animate-in fade-in duration-700` + `truncate` so a long message ellipsizes instead of scrolling.)

- [ ] **Step 4: Verify the build compiles**

Run: `cd crypto-trading-dashboard && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Verify no references to the deleted animation classes remain**

Run: `grep -rn "animate-chatbot-breathe\|animate-broadcast-marquee" crypto-trading-dashboard/app crypto-trading-dashboard/components`
Expected: no matches.

- [ ] **Step 6: Commit**

```bash
cd crypto-trading-dashboard
git add app/globals.css components/trading-chatbot.tsx
git commit -m "Replace chatbot breathing pulse and broadcast marquee with steady glow and fade-in"
```

---

### Task 4: Move chart components onto standard chart-bull/chart-bear colors

**Files:**
- Modify: `crypto-trading-dashboard/components/signal-chart.tsx`
- Modify: `crypto-trading-dashboard/components/gex-wall-chart.tsx`
- Modify: `crypto-trading-dashboard/components/liquidation-heatmap-chart.tsx`
- Modify: `crypto-trading-dashboard/components/rsi2-technical-chart.tsx`
- Modify: `crypto-trading-dashboard/components/price-range-gauge.tsx`

**Interfaces:**
- Consumes: `--chart-bull`, `--chart-bull-foreground`, `--chart-bear`, `--chart-bear-foreground` and their `text-chart-bull`/`bg-chart-bull`/`border-chart-bull`/`fill-chart-bull`/`stroke-chart-bull`/`from-chart-bull`/`via-chart-bull`/`to-chart-bull` (and `-bear`) Tailwind utilities from Task 1.
- Produces: nothing new — these five files keep their existing exported component signatures (`SignalChart`, `GexWallChart`, `LiquidationHeatmapChart`, `Rsi2TechnicalChart`/whatever the file exports, `PriceRangeGauge`); only internal class names and `var(--long)`/`var(--short)` references change.

This is a **mechanical, whole-file rename** — every one of these five files is entirely inside the "technical chart, keep standard colors" exception from the design spec, so every `--long`/`--short`-derived reference in them (no exceptions) becomes the `--chart-bull`/`--chart-bear` equivalent. It is not a partial/context-sensitive edit.

- [ ] **Step 1: Run the rename on all five files**

```bash
cd crypto-trading-dashboard
for f in components/signal-chart.tsx components/gex-wall-chart.tsx components/liquidation-heatmap-chart.tsx components/rsi2-technical-chart.tsx components/price-range-gauge.tsx; do
  sed -i '' \
    -e 's/var(--long)/var(--chart-bull)/g' \
    -e 's/var(--short)/var(--chart-bear)/g' \
    -e 's/\btext-long-foreground\b/text-chart-bull-foreground/g' \
    -e 's/\bbg-long-foreground\b/bg-chart-bull-foreground/g' \
    -e 's/\bborder-long-foreground\b/border-chart-bull-foreground/g' \
    -e 's/\bfill-long-foreground\b/fill-chart-bull-foreground/g' \
    -e 's/\bstroke-long-foreground\b/stroke-chart-bull-foreground/g' \
    -e 's/\btext-short-foreground\b/text-chart-bear-foreground/g' \
    -e 's/\bbg-short-foreground\b/bg-chart-bear-foreground/g' \
    -e 's/\bborder-short-foreground\b/border-chart-bear-foreground/g' \
    -e 's/\bfill-short-foreground\b/fill-chart-bear-foreground/g' \
    -e 's/\bstroke-short-foreground\b/stroke-chart-bear-foreground/g' \
    -e 's/\btext-long\b/text-chart-bull/g' \
    -e 's/\bbg-long\b/bg-chart-bull/g' \
    -e 's/\bborder-long\b/border-chart-bull/g' \
    -e 's/\bfill-long\b/fill-chart-bull/g' \
    -e 's/\bstroke-long\b/stroke-chart-bull/g' \
    -e 's/\bfrom-long\b/from-chart-bull/g' \
    -e 's/\bvia-long\b/via-chart-bull/g' \
    -e 's/\bto-long\b/to-chart-bull/g' \
    -e 's/\btext-short\b/text-chart-bear/g' \
    -e 's/\bbg-short\b/bg-chart-bear/g' \
    -e 's/\bborder-short\b/border-chart-bear/g' \
    -e 's/\bfill-short\b/fill-chart-bear/g' \
    -e 's/\bstroke-short\b/stroke-chart-bear/g' \
    -e 's/\bfrom-short\b/from-chart-bear/g' \
    -e 's/\bvia-short\b/via-chart-bear/g' \
    -e 's/\bto-short\b/to-chart-bear/g' \
    "$f"
done
```

- [ ] **Step 2: Manually check for anything the automated rename missed**

The sed list above covers every Tailwind color-utility prefix confirmed in `signal-chart.tsx` and `price-range-gauge.tsx` (read in full while writing this plan). `gex-wall-chart.tsx`, `liquidation-heatmap-chart.tsx`, and `rsi2-technical-chart.tsx` were not read in full, so run a broader, prefix-agnostic check for stragglers:

```bash
grep -n -- "-long\b\|-short\b\|var(--long)\|var(--short)" \
  components/signal-chart.tsx \
  components/gex-wall-chart.tsx \
  components/liquidation-heatmap-chart.tsx \
  components/rsi2-technical-chart.tsx \
  components/price-range-gauge.tsx
```

Expected: no matches. If anything shows up (e.g. an unusual Tailwind utility prefix like `ring-long` or `decoration-short` that wasn't in the sed list, or a literal string unrelated to color like a variable named `longPeriod`), fix it by hand: rename genuine color-utility matches to the `chart-bull`/`chart-bear` equivalent following the same mapping (`long` → `chart-bull`, `short` → `chart-bear`); leave alone anything that isn't actually a color token (e.g. a variable/prop name that merely contains the substring "long" or "short").

- [ ] **Step 3: Verify the build compiles**

Run: `cd crypto-trading-dashboard && npm run build`
Expected: build succeeds — Tailwind resolves every renamed class because Task 1 already registered `chart-bull`/`chart-bear` in `@theme inline`.

- [ ] **Step 4: Manual verification**

Run: `cd crypto-trading-dashboard && npm run dev`, open a symbol with an active signal so `SignalChart` and `PriceRangeGauge` render, and toggle the theme switch from Task 2. Confirm the candlesticks/TP-SL lines/gauge gradient stay the same standard green/red in both light and dark mode (they must NOT shift to the sage/rose UI colors), while everything else on the page does shift.

- [ ] **Step 5: Commit**

```bash
git add components/signal-chart.tsx components/gex-wall-chart.tsx components/liquidation-heatmap-chart.tsx components/rsi2-technical-chart.tsx components/price-range-gauge.tsx
git commit -m "Move technical chart components onto theme-invariant chart-bull/chart-bear colors"
```

---

### Task 5: Remove the alert-triangle icon from disclaimer/error banners

**Files:**
- Modify: `crypto-trading-dashboard/components/trade-dashboard.tsx:7,870`
- Modify: `crypto-trading-dashboard/components/liquidation-heatmap-chart.tsx:1,164`
- Modify: `crypto-trading-dashboard/components/gex-wall-chart.tsx:1,246,253`
- Modify: `crypto-trading-dashboard/components/high-winrate-panel.tsx:5,82`
- Modify: `crypto-trading-dashboard/components/favorites-overview.tsx:3,100,134`
- Modify: `crypto-trading-dashboard/components/backtest-sandbox-panel.tsx:4,318,352,364,394,466`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — pure deletion, no signatures change.

Every occurrence follows the same shape: an `<AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />` (or, in the footer, `size-4`) as the first child of a `flex items-start gap-...` wrapper whose only other child is the message text. Delete the icon element and its import; leave the wrapper `flex`/`gap` classes as-is (harmless on a single child, not worth a separate class edit).

- [ ] **Step 1: `trade-dashboard.tsx` — footer disclaimer**

Remove `AlertTriangle,` from the multi-line lucide-react import (currently line 7 of the import block):

```tsx
// Before:
import {
  Activity,
  AlertTriangle,
  CandlestickChart,
  ...

// After:
import {
  Activity,
  CandlestickChart,
  ...
```

Remove the icon from the footer (around line 870):

```tsx
// Before:
      <footer className="mt-2 flex items-start gap-2 rounded-xl border border-border/60 bg-card/60 p-4 text-xs leading-relaxed text-muted-foreground">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <p>

// After:
      <footer className="mt-2 flex items-start gap-2 rounded-xl border border-border/60 bg-card/60 p-4 text-xs leading-relaxed text-muted-foreground">
        <p>
```

- [ ] **Step 2: `liquidation-heatmap-chart.tsx`**

Delete the whole import line (it's the only import from `lucide-react` in this file):

```tsx
// Delete this line entirely:
import { AlertTriangle } from "lucide-react"
```

Remove the icon (line 164):

```tsx
// Before:
      <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        資料是本機監聽開始運作後才累積的真實強平單，不是回推未平倉部位的理論清算價位——累積時間越長，密度圖越有參考價值。

// After:
      <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
        資料是本機監聽開始運作後才累積的真實強平單，不是回推未平倉部位的理論清算價位——累積時間越長，密度圖越有參考價值。
```

- [ ] **Step 3: `gex-wall-chart.tsx`**

Delete the whole import line (it's the only import from `lucide-react` in this file):

```tsx
// Delete this line entirely:
import { AlertTriangle } from "lucide-react"
```

Remove both icon occurrences:

```tsx
// Before (around line 246):
      {gammaFlipStrike === null && (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          此履約價區間內，累積 Net GEX 沒有出現正負轉折，目前抓不到明確的 Gamma 擠壓臨界點。

// After:
      {gammaFlipStrike === null && (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          此履約價區間內，累積 Net GEX 沒有出現正負轉折，目前抓不到明確的 Gamma 擠壓臨界點。
```

```tsx
// Before (around line 253):
      {flipOutOfRange && (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          Gamma 臨界點距離現價超過 {Math.round(ZOOM_PCT * 100)}%，已移出主戰區顯示範圍，改用邊緣箭頭標示方向。

// After:
      {flipOutOfRange && (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          Gamma 臨界點距離現價超過 {Math.round(ZOOM_PCT * 100)}%，已移出主戰區顯示範圍，改用邊緣箭頭標示方向。
```

- [ ] **Step 4: `high-winrate-panel.tsx`**

```tsx
// Before:
import { AlertTriangle, Target } from "lucide-react"

// After:
import { Target } from "lucide-react"
```

```tsx
// Before (around line 82):
        <div className="flex items-start gap-1.5 rounded-lg border border-amber-400/30 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          {listData.caveat}

// After:
        <div className="flex items-start gap-1.5 rounded-lg border border-amber-400/30 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200">
          {listData.caveat}
```

- [ ] **Step 5: `favorites-overview.tsx`**

```tsx
// Before:
import { AlertTriangle, Star, type LucideIcon } from "lucide-react"

// After:
import { Star, type LucideIcon } from "lucide-react"
```

```tsx
// Before (around line 100):
            <div className="flex items-start gap-1.5 rounded-lg border border-short/30 bg-short/[0.06] px-3 py-2 text-xs text-short">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              無法載入期權分析資料：{optionsError}

// After:
            <div className="flex items-start gap-1.5 rounded-lg border border-short/30 bg-short/[0.06] px-3 py-2 text-xs text-short">
              無法載入期權分析資料：{optionsError}
```

```tsx
// Before (around line 134):
            <div className="flex items-start gap-1.5 rounded-lg border border-short/30 bg-short/[0.06] px-3 py-2 text-xs text-short">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              無法載入美股 ORB 資料：{usStocksError}

// After:
            <div className="flex items-start gap-1.5 rounded-lg border border-short/30 bg-short/[0.06] px-3 py-2 text-xs text-short">
              無法載入美股 ORB 資料：{usStocksError}
```

- [ ] **Step 6: `backtest-sandbox-panel.tsx`**

```tsx
// Before:
import { AlertTriangle, Rocket, RefreshCw } from "lucide-react"

// After:
import { Rocket, RefreshCw } from "lucide-react"
```

Five icon occurrences, all the same shape — remove the `<AlertTriangle ... />` line in each of these four blocks (around lines 318, 352, 364, 394, 466):

```tsx
// Before (line 318):
        <div className="flex items-start gap-1.5 rounded-lg border border-short/30 bg-short/[0.06] px-3 py-2 text-xs text-short">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          {error}

// After:
        <div className="flex items-start gap-1.5 rounded-lg border border-short/30 bg-short/[0.06] px-3 py-2 text-xs text-short">
          {error}
```

```tsx
// Before (line 352):
        <div className="flex items-start gap-1.5 rounded-lg border border-short/30 bg-short/[0.06] px-3 py-2 text-xs text-short">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          樣本數僅 {result.totalTrades} 筆（門檻15筆），這組數字統計上不具意義，不能拿來下結論。

// After:
        <div className="flex items-start gap-1.5 rounded-lg border border-short/30 bg-short/[0.06] px-3 py-2 text-xs text-short">
          樣本數僅 {result.totalTrades} 筆（門檻15筆），這組數字統計上不具意義，不能拿來下結論。
```

```tsx
// Before (line 364):
        <div className="flex items-start gap-1.5 rounded-lg border border-amber-400/30 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          {result.strategyCaveat}

// After:
        <div className="flex items-start gap-1.5 rounded-lg border border-amber-400/30 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200">
          {result.strategyCaveat}
```

```tsx
// Before (line 394):
      <div className="flex items-start gap-1.5 rounded-lg border border-amber-400/30 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200">
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        {result.caveat}

// After:
      <div className="flex items-start gap-1.5 rounded-lg border border-amber-400/30 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200">
        {result.caveat}
```

```tsx
// Before (line 466):
      <div className="flex items-start gap-1.5 rounded-lg border border-amber-400/30 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200">
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        {result.caveat}

// After:
      <div className="flex items-start gap-1.5 rounded-lg border border-amber-400/30 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200">
        {result.caveat}
```

- [ ] **Step 7: Verify no references to `AlertTriangle` remain anywhere**

Run: `grep -rn "AlertTriangle" crypto-trading-dashboard/app crypto-trading-dashboard/components`
Expected: no matches.

- [ ] **Step 8: Verify the build compiles**

Run: `cd crypto-trading-dashboard && npm run build`
Expected: build succeeds (no unused-import lint errors, since every import line above was edited to drop exactly `AlertTriangle` and nothing else).

- [ ] **Step 9: Commit**

```bash
cd crypto-trading-dashboard
git add components/trade-dashboard.tsx components/liquidation-heatmap-chart.tsx components/gex-wall-chart.tsx components/high-winrate-panel.tsx components/favorites-overview.tsx components/backtest-sandbox-panel.tsx
git commit -m "Drop alert-triangle icon from disclaimer and error banners, let text weight carry it"
```

---

### Task 6: End-to-end manual QA pass

**Files:** none (verification only, no commit).

**Interfaces:** none.

- [ ] **Step 1: Start the full stack**

Run the backend (`uvicorn main:app --reload --port 8000` from the repo root) and the frontend (`cd crypto-trading-dashboard && npm run dev`), or use this project's `run` skill if one is already configured, so real signal data is available (several banners/charts only render meaningfully with live data).

- [ ] **Step 2: Walk every tab in light mode (Sand & Sage)**

Open `http://localhost:3000`, confirm the theme toggle shows the sun icon is *not* active (light mode default on first load with no stored preference matching system light), and click through 總覽 / 加密貨幣 (主流幣 + 市場掃描) / 迷因雷達 / 迷因當沖 / 美股 ORB / 期權分析 / 高勝率策略 / 新聞輿情 / 回測沙盒. Confirm: no leftover pure-black or pure-white panels, LONG/SHORT badges read as sage/rose (not the old saturated green/red), and no disclaimer/error banner shows a triangle icon.

- [ ] **Step 3: Toggle to dark mode (Warm Charcoal) and repeat**

Click the theme toggle, confirm it switches instantly with no flash, and spot-check 3-4 of the same tabs — confirm the background is a warm dark charcoal (not the old pure near-black) and badges are still legible.

- [ ] **Step 4: Confirm the chart carve-out**

On 主流幣 or 美股 ORB with an open signal, confirm the candlestick chart and price-range gauge show standard vivid green/red in *both* light and dark mode (unchanged when toggling theme), while the card chrome around them (border, background) still follows the active theme.

- [ ] **Step 5: Confirm the calmer chatbot**

Open the collapsed AI chatbot button — confirm it shows a steady soft ring, not a pulsing halo. If a broadcast item is available, confirm new messages fade in rather than scroll across.

- [ ] **Step 6: Report results**

Note any visual regressions found (e.g. a color that reads as low-contrast, a leftover icon) back before considering this plan complete — fix forward with a small follow-up commit on the relevant task's files rather than reopening earlier tasks.

---

## Self-Review Notes

- **Spec coverage:** Color system → Task 1. Dark-mode-not-pure-black + toggle → Task 2. Chart color exception → Task 4. Chatbot breathing/marquee → Task 3. Alert-triangle removal → Task 5. Full-site rollout scope → all tasks touch every component that used `--long`/`--short`; Task 6 walks every tab. No spec section is unaddressed.
- **Placeholder scan:** every step has literal code or an exact command; no "add appropriate styling" phrasing anywhere.
- **Type consistency:** `Theme`, `THEME_STORAGE_KEY`, `getActiveTheme`, `applyTheme` are defined once in Task 2 Step 1 and used with those exact names in Steps 2-3 of the same task; no other task references them.
