import { kes, km } from "@/lib/format";

import type { CarProps } from "./CarCard";

const ROWS: { label: string; get: (c: CarProps) => string; lowerBetter?: boolean }[] = [
  { label: "Price", get: (c) => kes(c.price_kes) },
  { label: "Year", get: (c) => String(c.year) },
  { label: "Mileage", get: (c) => km(c.mileage_km), lowerBetter: true },
  { label: "Transmission", get: (c) => c.transmission },
  { label: "Body", get: (c) => c.body_type },
  { label: "Condition", get: (c) => c.condition },
  { label: "Location", get: (c) => c.location },
];

export default function ComparisonTable({ cars }: { cars: CarProps[] }) {
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
          {ROWS.map((row) => (
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
