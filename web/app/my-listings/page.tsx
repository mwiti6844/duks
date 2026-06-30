"use client";

import { useEffect, useState } from "react";
import type { CarProps } from "@/components/generative/CarCard";
import CarCard from "@/components/generative/CarCard";

export default function MyListingsPage() {
  const [cars, setCars] = useState<CarProps[]>([]);
  const [draft, setDraft] = useState<{ draft_id: string; progress: number } | null>(null);
  useEffect(() => {
    fetch("/api/listings").then((r) => r.json()).then(setCars);
    fetch("/api/listing-drafts/active").then((r) => r.json()).then(setDraft);
  }, []);
  return (
    <main className="mx-auto min-h-screen max-w-5xl p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-ink">My listings</h1>
        <a href="/chat" className="rounded border border-card-border px-3 py-2 text-sm">Back to assistant</a>
      </div>
      {draft && (
        <a href="/chat" className="mt-5 block rounded-xl border border-brand bg-brand/10 p-4 text-sm text-ink">
          Resume saved listing draft · {draft.progress}% complete →
        </a>
      )}
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cars.map((car) => <CarCard key={car.id} car={car} />)}
      </div>
      {!cars.length && <p className="mt-8 text-muted">You have no published listings yet.</p>}
    </main>
  );
}
