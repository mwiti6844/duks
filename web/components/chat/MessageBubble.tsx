import { renderComponent } from "@/lib/componentRegistry";
import type { ChatMessage, UIAction } from "@/lib/types";

import TracePanel from "./TracePanel";

export default function MessageBubble({
  message,
  onAction,
}: {
  message: ChatMessage;
  onAction?: (label: string, action: UIAction) => void;
}) {
  const isUser = message.role === "user";

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
        {message.text && (
          <div className="prose-sm whitespace-pre-wrap text-ink">
            {message.text}
            {message.streaming && !message.text && <TypingDots />}
          </div>
        )}
        {message.streaming && !message.text && message.components.length === 0 && <TypingDots />}

        {message.components.map((c, i) => (
          <div key={i}>{renderComponent(c, `${message.id}-${i}`, onAction)}</div>
        ))}

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
