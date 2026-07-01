import { kes, km } from "@/lib/format";

import type { CarProps } from "./CarCard";

const ROWS: { label: string; group: string; get: (c: CarProps) => string }[] = [
  { label: "Price", group: "price", get: (c) => kes(c.price_kes) },
  { label: "Year", group: "identity", get: (c) => String(c.year) },
  { label: "Trim", group: "identity", get: (c) => c.trim || "—" },
  { label: "Mileage", group: "mileage", get: (c) => km(c.mileage_km) },
  { label: "Engine", group: "engine", get: (c) => c.engine_cc ? `${c.engine_cc.toLocaleString()} CC` : "—" },
  { label: "Transmission", group: "transmission", get: (c) => c.transmission },
  { label: "Fuel", group: "fuel", get: (c) => c.fuel },
  { label: "Body", group: "body", get: (c) => c.body_type },
  { label: "Colour", group: "color", get: (c) => c.color || "—" },
  { label: "Condition", group: "condition", get: (c) => c.condition },
  { label: "Location", group: "location", get: (c) => c.location },
  { label: "Monthly estimate", group: "finance", get: (c) => c.monthly_payment_kes ? kes(c.monthly_payment_kes) : "—" },
];

export default function ComparisonTable({
  cars,
  fact_groups = [],
}: {
  cars: CarProps[];
  fact_groups?: string[];
}) {
  const [a, b] = cars;
  const cheaper = a.price_kes <= b.price_kes ? 0 : 1;
  const newer = a.year >= b.year ? 0 : 1;
  const lowerMileage = a.mileage_km <= b.mileage_km ? 0 : 1;

  function highlight(rowLabel: string, idx: number): boolean {
    if (rowLabel === "Price") return idx === cheaper;
    if (rowLabel === "Year") return idx === newer;
    if (rowLabel === "Mileage") return idx === lowerMileage;
    return false;
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50">
            <th className="p-3 text-left font-medium text-slate-500">Spec</th>
            {cars.map((c) => (
              <th key={c.id} className="p-3 text-left font-semibold text-ink">
                {c.year} {c.make} {c.model}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.filter((row) => fact_groups.length === 0 || fact_groups.includes(row.group)).map((row) => (
            <tr key={row.label} className="border-b border-slate-100 last:border-0">
              <td className="p-3 text-slate-500">{row.label}</td>
              {cars.map((c, idx) => (
                <td
                  key={c.id}
                  className={
                    "p-3 " +
                    (highlight(row.label, idx)
                      ? "bg-brand/15 font-semibold text-ink"
                      : "text-ink")
                  }
                >
                  {row.get(c)}
                  {highlight(row.label, idx) && (
                    <span className="ml-1.5 text-xs">✓</span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
