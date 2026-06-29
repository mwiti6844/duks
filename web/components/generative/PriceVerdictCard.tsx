import { kes, km } from "@/lib/format";

import type { CarProps } from "./CarCard";

interface Evidence {
  sale_id: string;
  sold_price_kes: number;
  year: number;
  mileage_km: number;
}

interface VerdictProps {
  car: CarProps;
  verdict: "fair" | "below_market" | "above_market" | "insufficient_data";
  asking_price_kes: number;
  comparable_median_kes?: number;
  comparable_low_kes?: number;
  comparable_high_kes?: number;
  delta_pct?: number;
  evidence: Evidence[];
}

const STYLES: Record<string, { label: string; badge: string; icon: string }> = {
  fair: { label: "Fairly priced", badge: "bg-emerald-100 text-emerald-700", icon: "✅" },
  below_market: { label: "Below market", badge: "bg-blue-100 text-blue-700", icon: "💎" },
  above_market: { label: "Above market", badge: "bg-amber-100 text-amber-700", icon: "⚠️" },
  insufficient_data: { label: "Not enough data", badge: "bg-slate-100 text-slate-600", icon: "❓" },
};

export default function PriceVerdictCard(p: VerdictProps) {
  const s = STYLES[p.verdict] ?? STYLES.insufficient_data;
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 p-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-400">AI Price Verdict</p>
          <h3 className="font-semibold text-ink">
            {p.car.year} {p.car.make} {p.car.model}
          </h3>
        </div>
        <span className={`rounded-full px-3 py-1 text-sm font-medium ${s.badge}`}>
          {s.icon} {s.label}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-4">
        <Stat label="Asking" value={kes(p.asking_price_kes)} accent />
        <Stat label="Comparable median" value={kes(p.comparable_median_kes)} />
        <Stat label="Range low" value={kes(p.comparable_low_kes)} />
        <Stat label="Range high" value={kes(p.comparable_high_kes)} />
      </div>

      {typeof p.delta_pct === "number" && (
        <p className="px-4 pb-2 text-sm text-slate-600">
          This price is{" "}
          <span className="font-semibold text-ink">
            {p.delta_pct > 0 ? "+" : ""}
            {p.delta_pct}%
          </span>{" "}
          vs. the median of recent comparable sales.
        </p>
      )}

      {p.evidence.length > 0 && (
        <details className="border-t border-slate-100 px-4 py-3 text-sm">
          <summary className="cursor-pointer font-medium text-slate-600">
            Evidence — {p.evidence.length} comparable sales
          </summary>
          <ul className="mt-2 space-y-1 text-slate-600">
            {p.evidence.map((e) => (
              <li key={e.sale_id} className="flex justify-between">
                <span className="text-slate-400">{e.sale_id}</span>
                <span>
                  {e.year} · {km(e.mileage_km)} · sold {kes(e.sold_price_kes)}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <p className="text-xs text-slate-400">{label}</p>
      <p className={"font-semibold " + (accent ? "text-ink" : "text-soft-ink")}>{value}</p>
    </div>
  );
}
