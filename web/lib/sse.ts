// SSE consumer using fetch + ReadableStream. EventSource can't send an authenticated
// POST, so the chat stream is read manually here. The auth cookie rides along
// automatically (same-origin), and the BFF proxy injects the Bearer token.

export interface SseEvent {
  event: string;
  data: Record<string, unknown>;
}

export async function streamChat(
  message: string,
  sessionId: string,
  onEvent: (ev: SseEvent) => void,
  action?: UIAction,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify({ message, session_id: sessionId, action }),
    signal,
  });
  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => "");
    throw new Error(`Chat request failed (${res.status}) ${detail}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      parseFrame(frame, onEvent);
    }
  }
  if (buffer.trim()) parseFrame(buffer, onEvent);
}

function parseFrame(frame: string, onEvent: (ev: SseEvent) => void): void {
  let event = "message";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return;
  try {
    onEvent({ event, data: JSON.parse(data) });
  } catch {
    /* ignore malformed frame */
  }
}
import type { UIAction } from "./types";
