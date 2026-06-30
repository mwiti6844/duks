export default function ListingProgress({
  percent,
  missing_fields,
}: {
  draft_id?: string;
  percent: number;
  missing_fields: string[];
  status?: string;
}) {
  return (
    <div className="rounded-xl border border-card-border bg-white p-3">
      <div className="flex justify-between text-xs font-medium text-ink">
        <span>Listing progress</span><span>{percent}%</span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface">
        <div className="h-full rounded-full bg-brand" style={{ width: `${percent}%` }} />
      </div>
      {missing_fields.length > 0 && (
        <p className="mt-2 text-xs text-muted">
          Still needed: {missing_fields.map((item) => item.replaceAll("_", " ")).join(", ")}
        </p>
      )}
    </div>
  );
}
