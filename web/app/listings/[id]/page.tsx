"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import CarCard, { CarProps } from "@/components/generative/CarCard";

export default function ListingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [car, setCar] = useState<CarProps | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    fetch(`/api/listings/${id}`).then(async (r) => {
      if (!r.ok) throw new Error("Listing not found");
      return r.json();
    }).then(setCar).catch((e) => setError(e.message));
  }, [id]);
  async function edit() {
    const res = await fetch(`/api/listings/${id}/edit`, { method: "POST" });
    if (res.ok) router.push("/chat");
  }
  return (
    <main className="mx-auto min-h-screen max-w-3xl p-6">
      <div className="mb-6 flex justify-between">
        <a href="/my-listings" className="text-sm text-muted">← My listings</a>
        <button onClick={edit} className="rounded bg-brand px-3 py-2 text-sm font-semibold text-ink">Edit listing</button>
      </div>
      {car && <CarCard car={car} />}
      {error && <p className="text-red-600">{error}</p>}
    </main>
  );
}
