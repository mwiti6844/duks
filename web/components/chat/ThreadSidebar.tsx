"use client";

import { useState } from "react";

import type { ConversationThread } from "@/lib/types";

interface Props {
  threads: ConversationThread[];
  activeThreadId: string | null;
  onNew: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
}

function relativeTime(value: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 60) return "now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

export default function ThreadSidebar({
  threads,
  activeThreadId,
  onNew,
  onSelect,
  onDelete,
  onRename,
}: Props) {
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const visible = threads.filter((thread) =>
    thread.title.toLowerCase().includes(query.trim().toLowerCase()),
  );
  return (
    <aside className="hidden h-screen w-72 shrink-0 flex-col border-r border-card-border bg-white md:flex">
      <div className="p-3">
        <button
          onClick={onNew}
          className="w-full rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-ink hover:bg-brand-light"
        >
          ＋ New conversation
        </button>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search conversations"
          aria-label="Search conversations"
          className="mt-2 w-full rounded-lg border border-card-border px-3 py-2 text-xs text-ink outline-none focus:border-brand"
        />
      </div>
      <div className="scroll-thin flex-1 overflow-y-auto px-2 pb-3">
        <p className="px-2 pb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
          Conversations
        </p>
        {visible.length === 0 && (
          <p className="px-2 py-4 text-xs text-muted">No conversations yet.</p>
        )}
        {visible.map((thread) => (
          <div
            key={thread.id}
            className={`group mb-1 flex items-center rounded-lg ${
              activeThreadId === thread.id ? "bg-brand/15" : "hover:bg-slate-50"
            }`}
          >
            {editingId === thread.id ? (
              <form
                className="min-w-0 flex-1 px-2 py-1.5"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (draftTitle.trim()) onRename(thread.id, draftTitle.trim());
                  setEditingId(null);
                }}
              >
                <input
                  autoFocus
                  value={draftTitle}
                  onChange={(event) => setDraftTitle(event.target.value)}
                  onBlur={() => setEditingId(null)}
                  className="w-full rounded border border-brand bg-white px-2 py-1 text-xs text-ink outline-none"
                />
              </form>
            ) : (
              <button
                onClick={() => onSelect(thread.id)}
                className="min-w-0 flex-1 px-3 py-2 text-left"
              >
                <span className="block truncate text-sm text-ink">{thread.title}</span>
                <span className="text-[11px] text-muted">
                  {relativeTime(thread.last_message_at)}
                </span>
              </button>
            )}
            <button
              onClick={() => {
                setDraftTitle(thread.title);
                setEditingId(thread.id);
              }}
              aria-label={`Rename ${thread.title}`}
              className="hidden rounded px-1 py-1 text-xs text-muted hover:bg-white group-hover:block"
            >
              ✎
            </button>
            <button
              onClick={() => {
                if (window.confirm(`Delete “${thread.title}”?`)) onDelete(thread.id);
              }}
              aria-label={`Delete ${thread.title}`}
              className="mr-2 hidden rounded px-1.5 py-1 text-xs text-muted hover:bg-red-50 hover:text-red-600 group-hover:block"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}
