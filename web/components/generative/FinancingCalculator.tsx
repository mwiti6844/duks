"use client";

import { useEffect, useState } from "react";

import { kes } from "@/lib/format";

import type { CarProps } from "./CarCard";

interface Plan {
  price_kes: number;
  deposit_kes: number;
  deposit_pct: number;
  financed_kes: number;
  term_months: number;
  annual_rate_pct: number;
  monthly_payment_kes: number;
  total_payable_kes: number;
  meets_min_deposit: boolean;
  min_deposit_kes: number;
}

interface Props extends Plan {
  car: CarProps | null;
}

export default function FinancingCalculator(initial: Props) {
  const price = initial.price_kes;
  const [depositPct, setDepositPct] = useState(initial.deposit_pct || 20);
  const [term, setTerm] = useState(initial.term_months || 48);
  const [plan, setPlan] = useState<Plan>(initial);
  const [busy, setBusy] = useState(false);

  // Recompute server-side whenever the sliders move (debounced).
  useEffect(() => {
    let cancel = false;
    const t = setTimeout(async () => {
      setBusy(true);
      try {
        const res = await fetch("/api/financing", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            principal_kes: price,
            deposit_kes: Math.round((depositPct / 100) * price),
            term_months: term,
          }),
        });
        if (res.ok && !cancel) setPlan(await res.json());
      } finally {
        if (!cancel) setBusy(false);
      }
    }, 250);
    return () => {
      cancel = true;
      clearTimeout(t);
    };
  }, [depositPct, term, price, initial.annual_rate_pct]);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold text-ink">
          Financing{initial.car ? ` · ${initial.car.make} ${initial.car.model}` : ""}
        </h3>
        <span className="text-xs text-slate-400">NCBA-backed · {plan.annual_rate_pct}% p.a.</span>
      </div>

      <div className="rounded-lg bg-brand/15 p-4 text-center">
        <p className="text-xs uppercase tracking-wide text-slate-400">Monthly payment</p>
        <p className="text-3xl font-bold text-ink">
          {kes(plan.monthly_payment_kes)}
          {busy && <span className="ml-2 text-sm text-slate-400">…</span>}
        </p>
        <p className="mt-1 text-xs text-slate-500">
          over {plan.term_months} months · total {kes(plan.total_payable_kes)}
        </p>
      </div>

      <div className="mt-4 space-y-4">
        <Slider
          label={`Deposit — ${depositPct}% (${kes(Math.round((depositPct / 100) * price))})`}
          min={10}
          max={60}
          value={depositPct}
          onChange={setDepositPct}
        />
        <Slider
          label={`Term — ${term} months`}
          min={12}
          max={72}
          step={6}
          value={term}
          onChange={setTerm}
        />
      </div>

      {!plan.meets_min_deposit && (
        <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-700">
          Minimum deposit is {kes(plan.min_deposit_kes)} (20%). Raise the deposit to qualify.
        </p>
      )}
    </div>
  );
}

function Slider({
  label,
  min,
  max,
  step = 1,
  value,
  onChange,
}: {
  label: string;
  min: number;
  max: number;
  step?: number;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="block">
      <span className="text-sm text-slate-600">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 w-full accent-brand"
      />
    </label>
  );
}
