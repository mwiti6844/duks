"use client";

import { useEffect, useState } from "react";

import BrandMark from "./BrandMark";

// SSR renders this when the api isn't ready yet. It polls /api/health (through the
// BFF proxy) and reloads the page once the api flips to ready, so the user lands on
// login/chat only against a fully seeded backend.
export default function ReadinessGate() {
  const [attempts, setAttempts] = useState(0);

  useEffect(() => {
    let active = true;
    const tick = async () => {
      try {
        const res = await fetch("/api/health", { cache: "no-store" });
        const data = await res.json().catch(() => ({}));
        if (active && data?.status === "ready") {
          window.location.reload();
          return;
        }
      } catch {
        /* keep polling */
      }
      if (active) setAttempts((a) => a + 1);
    };
    const id = setInterval(tick, 2000);
    tick();
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-light via-brand to-brand-dark px-6">
      <div className="w-full max-w-md rounded-2xl bg-white/95 p-8 text-center shadow-xl">
        <div className="mb-5 flex justify-center"><BrandMark /></div>
        <h1 className="text-xl font-semibold text-ink">Warming up CarDuka AI</h1>
        <p className="mt-2 text-sm text-muted">
          Seeding the marketplace and loading the knowledge base. This only takes a
          moment on first start…
        </p>
        <div className="mt-6 flex justify-center gap-1.5">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="typing-dot h-2.5 w-2.5 rounded-full bg-brand"
              style={{ animationDelay: `${i * 0.16}s` }}
            />
          ))}
        </div>
        <p className="mt-4 text-xs text-slate-400">checked {attempts} time(s)</p>
      </div>
    </main>
  );
}
