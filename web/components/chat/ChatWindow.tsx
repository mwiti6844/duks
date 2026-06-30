"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { useChat } from "@/lib/useChat";
import type { UIAction } from "@/lib/types";
import BrandMark from "@/components/BrandMark";

import Composer from "./Composer";
import EmptyChatState from "./EmptyChatState";
import MessageBubble from "./MessageBubble";

export default function ChatWindow() {
  const router = useRouter();
  const { messages, sending, send, sendAction, user } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showJourneys, setShowJourneys] = useState(false);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function exitToUsers() {
    await fetch("/api/auth/logout", { method: "POST" });
    localStorage.removeItem("carduka_sid");
    router.push("/login");
    router.refresh();
  }

  function startJourney(message: string, action: UIAction) {
    setShowJourneys(false);
    sendAction(message, action);
  }

  function sendMessage(message: string) {
    setShowJourneys(false);
    send(message);
  }

  return (
    <div className="mx-auto flex h-screen max-w-4xl flex-col">
      <header className="flex items-center justify-between border-b border-card-border bg-white px-4 py-3">
        <div className="flex items-center gap-2">
          <BrandMark compact />
          <span className="h-6 w-px bg-card-border" />
          <div>
            <h1 className="text-sm font-semibold text-ink">CarDuka AI Agent</h1>
            <p className="text-xs text-muted">NCBA-backed marketplace · demo</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {user && (
            <span className="hidden text-sm text-muted sm:inline">{user.full_name}</span>
          )}
          {messages.length > 0 && !showJourneys && (
            <button
              onClick={() => setShowJourneys(true)}
              className="rounded-lg border border-card-border px-3 py-1 text-xs text-muted hover:bg-brand/10"
            >
              ← Journeys
            </button>
          )}
          <a
            href="/my-listings"
            className="hidden rounded-lg border border-card-border px-3 py-1 text-xs text-muted hover:bg-brand/10 sm:inline"
          >
            My listings
          </a>
          <button
            onClick={exitToUsers}
            className="rounded-lg border border-card-border px-3 py-1 text-xs text-muted hover:bg-brand/10"
          >
            Exit
          </button>
        </div>
      </header>

      <div ref={scrollRef} className="scroll-thin flex-1 space-y-5 overflow-y-auto px-4 py-5">
        {messages.length === 0 || showJourneys ? (
          <EmptyChatState onAction={startJourney} disabled={sending} user={user} />
        ) : (
          messages.map((m) => (
            <MessageBubble
              key={m.id}
              message={m}
              onAction={sending ? undefined : sendAction}
            />
          ))
        )}
      </div>

      <Composer onSend={sendMessage} disabled={sending} />
    </div>
  );
}
