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
