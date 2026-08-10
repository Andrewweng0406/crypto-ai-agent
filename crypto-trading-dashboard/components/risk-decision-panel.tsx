import { ShieldAlert } from "lucide-react"
import { cn } from "@/lib/utils"
import { type Signal, formatPrice } from "@/lib/signals"
import { assessSignalRisk, type RiskLevel } from "@/lib/risk"

const riskStyles: Record<RiskLevel, string> = {
  low: "border-long/30 bg-long/[0.07] text-long",
  medium: "border-amber-400/40 bg-amber-400/10 text-amber-700 dark:text-amber-300",
  high: "border-short/30 bg-short/[0.07] text-short",
  critical: "border-short/50 bg-short/[0.12] text-short",
}

export function RiskDecisionPanel({ signal }: { signal: Signal }) {
  const risk = assessSignalRisk(signal)

  return (
    <section className={cn("rounded-2xl border p-5", riskStyles[risk.level])}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShieldAlert className="size-5" aria-hidden="true" />
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide">風險判讀</h2>
            <p className="text-xl font-bold text-foreground">{risk.decision}</p>
          </div>
        </div>
        <span className="rounded-full bg-background/70 px-3 py-1 text-xs font-semibold">{risk.label}</span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2">
        <Metric label="到停損" value={`-${risk.stopMovePct.toFixed(2)}%`} />
        <Metric label="槓桿後停損" value={`-${risk.leveragedLossPct.toFixed(2)}%`} />
        <Metric label="到停利" value={`+${risk.rewardMovePct.toFixed(2)}%`} />
        <Metric label="盈虧比" value={`1 : ${risk.riskRewardRatio.toFixed(2)}`} />
      </div>

      <p className="mt-3 text-xs leading-relaxed opacity-85">
        進場 ${formatPrice(signal.entry_price)}，停損 ${formatPrice(signal.sl)}。真正下單前，單筆最大虧損應先限制在帳戶
        1% 左右。
      </p>

      {risk.notes.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1.5 text-xs leading-relaxed">
          {risk.notes.slice(0, 3).map((note) => (
            <li key={note}>• {note}</li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border/50 bg-background/60 px-3 py-2">
      <span className="block text-[11px] text-muted-foreground">{label}</span>
      <span className="font-mono text-sm font-bold text-foreground">{value}</span>
    </div>
  )
}
