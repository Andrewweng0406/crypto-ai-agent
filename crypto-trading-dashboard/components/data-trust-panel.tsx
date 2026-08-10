import { AlertTriangle, CheckCircle2, Clock3, WifiOff } from "lucide-react"
import { cn } from "@/lib/utils"
import { type DataTrustItem, type TrustLevel } from "@/lib/risk"

const trustStyles: Record<TrustLevel, { label: string; className: string; icon: typeof CheckCircle2 }> = {
  live: { label: "即時", className: "border-long/30 bg-long/[0.08] text-long", icon: CheckCircle2 },
  delayed: { label: "延遲", className: "border-primary/30 bg-primary/[0.08] text-foreground", icon: Clock3 },
  experimental: { label: "實驗", className: "border-amber-400/40 bg-amber-400/10 text-amber-700 dark:text-amber-300", icon: AlertTriangle },
  offline: { label: "離線", className: "border-short/30 bg-short/[0.07] text-short", icon: WifiOff },
}

export function DataTrustPanel({ items }: { items: DataTrustItem[] }) {
  return (
    <section className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((item) => {
        const style = trustStyles[item.level]
        const Icon = style.icon
        return (
          <div key={item.label} className={cn("rounded-xl border px-3 py-3", style.className)}>
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-xs font-semibold uppercase">{item.label}</span>
              <span className="inline-flex items-center gap-1 rounded-full bg-background/60 px-2 py-0.5 text-[11px] font-semibold">
                <Icon className="size-3" aria-hidden="true" />
                {style.label}
              </span>
            </div>
            <p className="mt-2 text-xs leading-relaxed opacity-85">{item.detail}</p>
          </div>
        )
      })}
    </section>
  )
}
