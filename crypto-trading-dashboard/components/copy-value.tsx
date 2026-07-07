"use client"

import { useState } from "react"
import { Check, Copy } from "lucide-react"
import { cn } from "@/lib/utils"

interface CopyValueProps {
  value: number | string
  label: string
  className?: string
}

export function CopyValue({ value, label, className }: CopyValueProps) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    const text = String(value)
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // Fallback for browsers without clipboard permissions
      const el = document.createElement("textarea")
      el.value = text
      document.body.appendChild(el)
      el.select()
      document.execCommand("copy")
      document.body.removeChild(el)
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 1400)
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={`Copy ${label}`}
      className={cn(
        "inline-flex size-7 shrink-0 items-center justify-center rounded-md border border-border/60 bg-secondary/60 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
        className,
      )}
    >
      {copied ? (
        <Check className="size-3.5 text-long" aria-hidden="true" />
      ) : (
        <Copy className="size-3.5" aria-hidden="true" />
      )}
      <span className="sr-only">{copied ? "Copied!" : `Copy ${label}`}</span>
    </button>
  )
}
