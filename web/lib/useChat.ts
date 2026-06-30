"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { streamChat } from "./sse";
import type { ChatMessage, DemoUser, GenComponent, UIAction } from "./types";

function uid(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function getSessionId(): string {
  if (typeof window === "undefined") return "ssr";
  let sid = localStorage.getItem("carduka_sid");
  if (!sid) {
    sid = "sess_" + uid();
    localStorage.setItem("carduka_sid", sid);
  }
  return sid;
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [user, setUser] = useState<DemoUser | null>(null);
  const sidRef = useRef<string>("");
  const bootstrapped = useRef(false);
  const sendingRef = useRef(false);

  const updateLast = useCallback((fn: (m: ChatMessage) => ChatMessage) => {
    setMessages((prev) => {
      if (prev.length === 0) return prev;
      const copy = prev.slice();
      copy[copy.length - 1] = fn(copy[copy.length - 1]);
      return copy;
    });
  }, []);

  const sendInternal = useCallback(
    async (text: string, action?: UIAction) => {
      const trimmed = text.trim();
      if (!trimmed || sendingRef.current) return;
      const sid = sidRef.current;
      sendingRef.current = true;
      setSending(true);
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: "user", text: trimmed, components: [], trace: [], tools: [] },
        { id: uid(), role: "assistant", text: "", components: [], trace: [], tools: [], streaming: true },
      ]);
      try {
        await streamChat(trimmed, sid, (ev) => {
          if (ev.event === "token") {
            updateLast((m) => ({ ...m, text: m.text + (ev.data.text as string) }));
          } else if (ev.event === "component") {
            updateLast((m) => ({
              ...m,
              components: [...m.components, ev.data as unknown as GenComponent],
            }));
          } else if (ev.event === "trace") {
            updateLast((m) => ({ ...m, trace: [...m.trace, ev.data as never] }));
          } else if (ev.event === "tool") {
            updateLast((m) => ({ ...m, tools: [...m.tools, ev.data as never] }));
          } else if (ev.event === "error") {
            updateLast((m) => ({ ...m, text: m.text + `\n[error: ${ev.data.message}]` }));
          }
        }, action);
      } catch (e) {
        if (e instanceof Error && e.message.includes("(401)")) {
          localStorage.removeItem("carduka_sid");
          window.location.href = "/login";
          return;
        }
        updateLast((m) => ({
          ...m,
          text: m.text || `Something went wrong: ${e instanceof Error ? e.message : e}`,
        }));
      } finally {
        sendingRef.current = false;
        updateLast((m) => ({ ...m, streaming: false }));
        setSending(false);
      }
    },
    [updateLast],
  );

  const send = useCallback(
    (text: string) => sendInternal(text),
    [sendInternal],
  );

  const sendAction = useCallback(
    (label: string, action: UIAction) => sendInternal(label, action),
    [sendInternal],
  );

  // Bootstrap on mount: restore user and pending work. A fresh session remains
  // empty so the user chooses a journey card or writes the first message.
  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    sidRef.current = getSessionId();
    const sid = sidRef.current;
    (async () => {
      try {
        const res = await fetch(`/api/session/bootstrap?session_id=${encodeURIComponent(sid)}`, {
          cache: "no-store",
        });
        if (res.status === 401) {
          localStorage.removeItem("carduka_sid");
          window.location.href = "/login";
          return;
        }
        if (res.ok) {
          const data = await res.json();
          setUser(data.user);
          const restored: ChatMessage[] = [];
          const persisted = data.turns?.length ? data.turns : data.history || [];
          for (const h of persisted) {
            restored.push({
              id: h.id || uid(),
              role: h.role,
              text: h.text ?? h.content,
              components: h.components || [],
              trace: [],
              tools: [],
            });
          }
          if (data.pending_bid) {
            // Restore the unconfirmed bid modal after a refresh.
            restored.push({
              id: uid(),
              role: "assistant",
              text: "You have a pending bid awaiting confirmation:",
              components: [
                {
                  type: "bid_confirm_modal",
                  props: {
                    auction: data.pending_bid.auction,
                    signed_proposal: data.pending_bid.signed_proposal,
                    amount_kes: data.pending_bid.amount_kes,
                    meets_reserve: data.pending_bid.meets_reserve,
                    restored: true,
                  },
                },
              ],
              trace: [],
              tools: [],
            });
          }
          if (data.listing_draft && data.listing_draft.status === "ready_to_publish") {
            // Resume an unpublished reviewed sell flow after a refresh.
            const d = data.listing_draft;
            restored.push({
              id: uid(),
              role: "assistant",
              text: "You have an unpublished listing:",
              components: [
                {
                  type: "listing_summary",
                  props: {
                    ...d.fields,
                    draft_id: d.draft_id,
                    signed_draft: d.signed,
                    revision: d.revision,
                    status: d.status,
                    progress: 100,
                    validation: d.validation || [],
                    guidance: d.guidance || {},
                    images: d.images || [],
                    mode: d.mode || "create",
                    restored: true,
                  },
                },
              ],
              trace: [],
              tools: [],
            });
          } else if (data.listing_draft && data.listing_draft.status === "collecting") {
            const d = data.listing_draft;
            const missing = Object.entries(d.fields || {})
              .filter(([, value]) => !value)
              .map(([key]) => key);
            restored.push({
              id: uid(),
              role: "assistant",
              text: "Your saved listing draft is ready to continue. Tell me the next detail when you are ready.",
              components: [{
                type: "listing_progress",
                props: {
                  draft_id: d.draft_id,
                  percent: d.progress || 0,
                  missing_fields: d.missing_fields || missing,
                  status: d.status,
                },
              }],
              trace: [],
              tools: [],
            });
          }
          setMessages(restored);
        }
      } catch {
        /* ignore */
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { messages, sending, send, sendAction, user, sessionId: sidRef };
}
