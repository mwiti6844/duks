interface Citation {
  source_id: string;
  title: string;
  score: number;
  source_url?: string | null;
}

export default function KnowledgeAnswer({ citations }: { answer?: string; citations: Citation[] }) {
  if (!citations?.length) return null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
        Sources
      </p>
      <div className="flex flex-wrap gap-2">
        {citations.map((c) => (
          c.source_url ? (
            <a
              key={c.source_id}
              href={c.source_url}
              target="_blank"
              rel="noreferrer"
              title={`relevance ${c.score}`}
              className="inline-flex items-center gap-1 rounded-full border border-brand bg-brand/15 px-3 py-1 text-xs text-ink hover:bg-brand/30"
            >
              <span>↗</span>
              {c.title}
            </a>
          ) : (
            <span
              key={c.source_id}
              title={`relevance ${c.score}`}
              className="inline-flex items-center gap-1 rounded-full border border-brand bg-brand/15 px-3 py-1 text-xs text-ink"
            >
              <span>📄</span>
              {c.title}
            </span>
          )
        ))}
      </div>
    </div>
  );
}
