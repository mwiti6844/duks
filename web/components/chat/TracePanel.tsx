"use client";

import { useState } from "react";

import type { ToolEvent, TraceEntry } from "@/lib/types";

// Collapsible, sanitized agent/tool trace. Shows routing, tool names + timings,
// validated params, citation ids, and prompt version — never prompts, secrets, or
// chain-of-thought (the backend only emits sanitized trace entries).
export default function TracePanel({
  trace,
  tools,
}: {
  trace: TraceEntry[];
  tools: ToolEvent[];
}) {
  const [open, setOpen] = useState(false);
  const completed = tools.filter((t) => t.status === "completed");
  if (trace.length === 0 && completed.length === 0) return null;

  const intent = trace.find((t) => t.label === "intent")?.detail?.intent as string | undefined;

  return (
    <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-3 py-1.5 text-slate-500 hover:text-slate-700"
      >
        <span className="flex items-center gap-2">
          <span>{open ? "▾" : "▸"}</span>
          <span>Agent trace</span>
          {intent && (
            <span className="rounded bg-brand/20 px-1.5 py-0.5 font-mono text-[10px] text-ink">
              {intent}
            </span>
          )}
          <span className="text-slate-400">· {completed.length} tool call(s)</span>
        </span>
      </button>

      {open && (
        <div className="space-y-2 border-t border-slate-200 px-3 py-2">
          {trace.length > 0 && (
            <div>
              <p className="mb-1 font-medium text-slate-500">Routing & retrieval</p>
              <ul className="space-y-0.5">
                {trace.map((t, i) => (
                  <li key={i} className="flex justify-between gap-2 font-mono text-[11px]">
                    <span className="text-slate-500">{t.kind}:{t.label}</span>
                    <span className="truncate text-slate-400">{compact(t.detail)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {completed.length > 0 && (
            <div>
              <p className="mb-1 font-medium text-slate-500">Tools</p>
              <ul className="space-y-0.5">
                {completed.map((t, i) => (
                  <li key={i} className="flex justify-between gap-2 font-mono text-[11px]">
                    <span className="text-slate-600">{t.name}</span>
                    <span className="text-slate-400">
                      {compact(t.detail)} · {t.ms}ms
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function compact(detail: Record<string, unknown> | undefined): string {
  if (!detail) return "";
  return Object.entries(detail)
    .map(([k, v]) => `${k}=${Array.isArray(v) ? `[${v.length}]` : JSON.stringify(v)}`)
    .join(" ")
    .slice(0, 80);
}
