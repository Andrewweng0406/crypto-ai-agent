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
