import { kes } from "@/lib/format";

export default function ListingPriceGuidance({ guidance }: { guidance: Record<string, unknown> }) {
  if (guidance.status !== "available") {
    return <p className="text-xs text-muted">Not enough sold comparables for price guidance.</p>;
  }
  return (
    <div className="rounded-lg bg-brand/10 p-3">
      <p className="text-xs font-semibold text-ink">Advisory price guidance</p>
      <p className="mt-1 text-sm text-ink">
        {kes(guidance.low_kes as number)} – {kes(guidance.high_kes as number)}
      </p>
      <p className="text-xs text-muted">
        Comparable median: {kes(guidance.median_kes as number)}. Guidance only—you control the price.
      </p>
    </div>
  );
}
