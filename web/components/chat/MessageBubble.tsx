import { renderComponent } from "@/lib/componentRegistry";
import type { ChatMessage, GenComponent, UIAction } from "@/lib/types";

import TracePanel from "./TracePanel";

// Generative components render in the assistant column (full width). Cap them so
// they stay readable instead of sprawling edge-to-edge: tables/grids get more
// room, a single detail card a little less, and everything else stays compact.
const WIDE_COMPONENTS = new Set([
  "comparison_table",
  "car_card_list",
  "auction_countdown",
]);
const MEDIUM_COMPONENTS = new Set(["vehicle_detail"]);

function componentMaxWidth(type: string): string {
  if (WIDE_COMPONENTS.has(type)) return "max-w-4xl";
  if (MEDIUM_COMPONENTS.has(type)) return "max-w-3xl";
  return "max-w-2xl";
}

export default function MessageBubble({
  message,
  onAction,
}: {
  message: ChatMessage;
  onAction?: (label: string, action: UIAction) => void;
}) {
  const isUser = message.role === "user";
  const blocks = message.blocks?.length
    ? message.blocks
    : [
        ...(message.text ? [{ type: "text" as const, text: message.text }] : []),
        ...message.components.map((component) => ({
          type: "component" as const,
          component_type: component.type,
          schema_version: 1,
          props: component.props,
        })),
      ];

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-brand px-4 py-2 text-ink">
          {message.text}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand/25 text-sm">
        🤖
      </div>
      <div className="min-w-0 flex-1 space-y-3">
        {blocks.map((block, i) =>
          block.type === "text" ? (
            <div key={i} className="prose-sm max-w-3xl whitespace-pre-wrap text-ink">
              {block.text}
            </div>
          ) : (
            <div key={i} className={componentMaxWidth(block.component_type)}>
              {renderComponent(
                { type: block.component_type, props: block.props } as GenComponent,
                `${message.id}-${i}`,
                onAction,
              )}
            </div>
          ),
        )}
        {message.streaming && blocks.length === 0 && <TypingDots />}

        <TracePanel trace={message.trace} tools={message.tools} />
      </div>
    </div>
  );
}

function TypingDots() {
  return (
    <span className="inline-flex gap-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="typing-dot h-1.5 w-1.5 rounded-full bg-slate-400"
          style={{ animationDelay: `${i * 0.16}s` }}
        />
      ))}
    </span>
  );
}
