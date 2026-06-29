"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import BrandMark from "@/components/BrandMark";

const DEMO_USERS = [
  { username: "david", name: "David Mwangi", location: "Nairobi", emoji: "🧑🏾" },
  { username: "sarah", name: "Sarah Wanjiru", location: "Kiambu", emoji: "👩🏾" },
];

export default function LoginPage() {
  const router = useRouter();
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function login(username: string) {
    setLoading(username);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ username, password: "demo1234" }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail || "Login failed");
      }
      router.push("/chat");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
      setLoading(null);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-light via-brand to-brand-dark px-6">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-xl">
        <div className="mb-6 text-center">
          <div className="mb-3 flex justify-center"><BrandMark /></div>
          <h1 className="text-2xl font-bold text-ink">CarDuka AI Agent</h1>
          <p className="mt-1 text-sm text-muted">
            Kenya&apos;s NCBA-backed car marketplace — pick a demo profile to sign in.
          </p>
        </div>

        <div className="space-y-3">
          {DEMO_USERS.map((u) => (
            <button
              key={u.username}
              onClick={() => login(u.username)}
              disabled={loading !== null}
              className="flex w-full items-center gap-4 rounded-xl border border-card-border p-4 text-left transition hover:border-brand hover:bg-brand/10 disabled:opacity-60"
            >
              <span className="text-3xl">{u.emoji}</span>
              <span className="flex-1">
                <span className="block font-semibold text-ink">{u.name}</span>
                <span className="block text-sm text-muted">CarDuka user · {u.location}</span>
              </span>
              <span className="text-sm font-semibold text-ink">
                {loading === u.username ? "Signing in…" : "Sign in →"}
              </span>
            </button>
          ))}
        </div>

        {error && <p className="mt-4 text-center text-sm text-red-600">{error}</p>}

        <p className="mt-6 text-center text-xs text-slate-400">
          Demo only · all data is seeded · password is pre-filled
        </p>
      </div>
    </main>
  );
}
