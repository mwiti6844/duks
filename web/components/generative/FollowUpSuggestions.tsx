"use client";

import type { FollowUpSuggestion, UIAction } from "@/lib/types";

export default function FollowUpSuggestions({
  suggestions,
  onAction,
  disabled = false,
}: {
  suggestions: FollowUpSuggestion[];
  onAction?: (label: string, action: UIAction) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-2 pt-1" aria-label="Suggested follow-up questions">
      {suggestions.map((item) => (
        <button
          key={item.id}
          type="button"
          disabled={disabled || !onAction}
          onClick={() => onAction?.(item.label, item.action)}
          className="rounded-xl border border-brand bg-brand/15 px-3 py-2 text-left text-xs font-medium text-ink transition hover:bg-brand/30 disabled:pointer-events-none disabled:opacity-60"
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
