"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { streamChat } from "./sse";
import type {
  ChatMessage,
  ConversationThread,
  DemoUser,
  GenComponent,
  MessageBlock,
  UIAction,
} from "./types";

function uid(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function legacySessionId(): string {
  let sid = localStorage.getItem("carduka_sid");
  if (!sid) {
    sid = "sess_" + uid();
    localStorage.setItem("carduka_sid", sid);
  }
  return sid;
}

function messageFromPersisted(item: {
  id: string;
  role: "user" | "assistant";
  content: MessageBlock[];
  trace?: ChatMessage["trace"];
  tools?: ChatMessage["tools"];
}): ChatMessage {
  const blocks = item.content || [];
  return {
    id: item.id,
    role: item.role,
    text: blocks.filter((block) => block.type === "text").map((block) => block.text).join(""),
    components: blocks
      .filter((block) => block.type === "component")
      .map((block) => ({
        type: block.component_type,
        props: block.props,
      })) as GenComponent[],
    blocks,
    trace: item.trace || [],
    tools: item.tools || [],
  };
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [threads, setThreads] = useState<ConversationThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [user, setUser] = useState<DemoUser | null>(null);
  const threadRef = useRef<string>("");
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

  const refreshThreads = useCallback(async () => {
    const res = await fetch("/api/threads?limit=50", { cache: "no-store" });
    if (!res.ok) return [];
    const data = await res.json();
    const items = (data.items || []) as ConversationThread[];
    setThreads(items);
    return items;
  }, []);

  const loadThread = useCallback(async (threadId: string) => {
    const res = await fetch(`/api/threads/${encodeURIComponent(threadId)}`, {
      cache: "no-store",
    });
    if (!res.ok) return false;
    const data = await res.json();
    setMessages((data.messages || []).map(messageFromPersisted));
    threadRef.current = threadId;
    setActiveThreadId(threadId);
    localStorage.setItem("carduka_active_thread_id", threadId);
    // Existing interactive components still use this compatibility key.
    localStorage.setItem("carduka_sid", threadId);
    return true;
  }, []);

  const createThread = useCallback(async () => {
    const res = await fetch("/api/threads", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!res.ok) throw new Error("Could not create a conversation");
    const thread = (await res.json()) as ConversationThread;
    setThreads((current) => [thread, ...current]);
    setMessages([]);
    threadRef.current = thread.id;
    setActiveThreadId(thread.id);
    localStorage.setItem("carduka_active_thread_id", thread.id);
    localStorage.setItem("carduka_sid", thread.id);
    return thread.id;
  }, []);

  const selectThread = useCallback(async (threadId: string) => {
    if (sendingRef.current || threadId === threadRef.current) return;
    await loadThread(threadId);
  }, [loadThread]);

  const deleteThread = useCallback(async (threadId: string) => {
    if (sendingRef.current) return;
    const res = await fetch(`/api/threads/${encodeURIComponent(threadId)}`, {
      method: "DELETE",
    });
    if (!res.ok) return;
    const remaining = threads.filter((thread) => thread.id !== threadId);
    setThreads(remaining);
    if (threadRef.current === threadId) {
      const next = remaining[0];
      if (next) {
        await loadThread(next.id);
      } else {
        threadRef.current = "";
        setActiveThreadId(null);
        setMessages([]);
        localStorage.removeItem("carduka_active_thread_id");
        localStorage.removeItem("carduka_sid");
      }
    }
  }, [loadThread, threads]);

  const renameThread = useCallback(async (threadId: string, title: string) => {
    const res = await fetch(`/api/threads/${encodeURIComponent(threadId)}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) return;
    const updated = (await res.json()) as ConversationThread;
    setThreads((current) =>
      current.map((thread) => thread.id === threadId ? updated : thread),
    );
  }, []);

  const sendInternal = useCallback(
    async (text: string, action?: UIAction) => {
      const trimmed = text.trim();
      if (!trimmed || sendingRef.current) return;
      let threadId = threadRef.current;
      if (!threadId) threadId = await createThread();
      sendingRef.current = true;
      setSending(true);
      const userBlock: MessageBlock = { type: "text", text: trimmed };
      setMessages((prev) => [
        ...prev,
        {
          id: uid(), role: "user", text: trimmed, components: [],
          blocks: [userBlock], trace: [], tools: [],
        },
        {
          id: uid(), role: "assistant", text: "", components: [],
          blocks: [], trace: [], tools: [], streaming: true,
        },
      ]);
      try {
        await streamChat(trimmed, threadId, (ev) => {
          if (ev.event === "token") {
            const delta = ev.data.text as string;
            updateLast((message) => {
              const blocks = [...(message.blocks || [])];
              const last = blocks[blocks.length - 1];
              if (last?.type === "text") last.text += delta;
              else blocks.push({ type: "text", text: delta });
              return { ...message, text: message.text + delta, blocks };
            });
          } else if (ev.event === "component") {
            const component = ev.data as unknown as GenComponent;
            updateLast((message) => ({
              ...message,
              components: [...message.components, component],
              blocks: [
                ...(message.blocks || []),
                {
                  type: "component",
                  component_type: component.type,
                  schema_version: 1,
                  props: component.props,
                },
              ],
            }));
          } else if (ev.event === "trace") {
            updateLast((message) => ({
              ...message,
              trace: [...message.trace, ev.data as never],
            }));
          } else if (ev.event === "tool") {
            updateLast((message) => ({
              ...message,
              tools: [...message.tools, ev.data as never],
            }));
          } else if (ev.event === "error") {
            const errorText = `\n[error: ${ev.data.message}]`;
            updateLast((message) => ({
              ...message,
              text: message.text + errorText,
              blocks: [...(message.blocks || []), { type: "text", text: errorText }],
            }));
          }
        }, action);
      } catch (error) {
        if (error instanceof Error && error.message.includes("(401)")) {
          localStorage.removeItem("carduka_sid");
          localStorage.removeItem("carduka_active_thread_id");
          window.location.href = "/login";
          return;
        }
        updateLast((message) => {
          const errorText = `Something went wrong: ${
            error instanceof Error ? error.message : error
          }`;
          return {
            ...message,
            text: message.text || errorText,
            blocks: message.blocks?.length
              ? message.blocks
              : [{ type: "text", text: errorText }],
          };
        });
      } finally {
        sendingRef.current = false;
        updateLast((message) => ({ ...message, streaming: false }));
        setSending(false);
        await refreshThreads();
        // Semantic titles are generated after the streamed response completes.
        window.setTimeout(() => void refreshThreads(), 1500);
        window.setTimeout(() => void refreshThreads(), 5000);
      }
    },
    [createThread, refreshThreads, updateLast],
  );

  const send = useCallback((text: string) => sendInternal(text), [sendInternal]);
  const sendAction = useCallback(
    (label: string, action: UIAction) => sendInternal(label, action),
    [sendInternal],
  );

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    (async () => {
      try {
        const available = await refreshThreads();
        const saved = localStorage.getItem("carduka_active_thread_id");
        const selected = available.find((thread) => thread.id === saved) || available[0];
        const bootstrapId = selected?.id || legacySessionId();
        const bootstrap = await fetch(
          `/api/session/bootstrap?session_id=${encodeURIComponent(bootstrapId)}`,
          { cache: "no-store" },
        );
        if (bootstrap.status === 401) {
          localStorage.removeItem("carduka_sid");
          localStorage.removeItem("carduka_active_thread_id");
          window.location.href = "/login";
          return;
        }
        if (bootstrap.ok) {
          const bootstrapData = await bootstrap.json();
          setUser(bootstrapData.user);
          if (!selected && bootstrapData.thread_id) {
            await refreshThreads();
            await loadThread(bootstrapData.thread_id);
            return;
          }
        }
        if (selected) await loadThread(selected.id);
      } catch {
        /* Readiness page and composer surface connectivity failures. */
      }
    })();
  }, [loadThread, refreshThreads]);

  return {
    messages,
    threads,
    activeThreadId,
    sending,
    send,
    sendAction,
    user,
    createThread,
    selectThread,
    deleteThread,
    renameThread,
    sessionId: threadRef,
  };
}
