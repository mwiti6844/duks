"use client";

import { useState } from "react";

import { kes, km } from "@/lib/format";

import CarImage from "./CarImage";

interface Props {
  draft_id: string;
  make: string;
  model: string;
  year: number;
  price_kes: number;
  mileage_km: number;
  transmission: string;
  fuel: string;
  condition: string;
  body_type: string;
  location: string;
  image_url?: string;
  signed_draft: Record<string, unknown>;
  restored?: boolean;
}

type Status = "pending" | "publishing" | "published" | "cancelled" | "error";

export default function ListingSummary(p: Props) {
  const [status, setStatus] = useState<Status>("pending");
  const [message, setMessage] = useState("");

  const sessionId =
    typeof window !== "undefined" ? localStorage.getItem("carduka_sid") || "" : "";

  async function confirm() {
    setStatus("publishing");
    try {
      const res = await fetch("/api/listings/confirm", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ signed_draft: p.signed_draft, session_id: sessionId }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.detail || "Could not publish the listing");
      setStatus("published");
      setMessage(
        data.created
          ? `Your listing is live on CarDuka. Listing ID: ${data.listing.id}`
          : `This listing was already published. Listing ID: ${data.listing.id}`,
      );
    } catch (e) {
      setStatus("error");
      setMessage(e instanceof Error ? e.message : "Publish failed");
    }
  }

  async function cancel() {
    setStatus("cancelled");
    try {
      await fetch("/api/listings/cancel", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch {
      /* best effort */
    }
  }

  return (
    <div className="overflow-hidden rounded-xl border-2 border-brand/30 bg-white shadow-md">
      <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
        <span className="text-lg">📋</span>
        <h3 className="font-semibold text-ink">Review your listing</h3>
        {p.restored && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
            resumed
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-[160px_1fr]">
        <CarImage make={p.make} model={p.model} image_url={p.image_url} className="h-28" />
        <div>
          <p className="text-lg font-semibold text-ink">
            {p.year} {p.make} {p.model}
          </p>
          <p className="text-xl font-bold text-ink">{kes(p.price_kes)}</p>
          <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-600">
            <div>{km(p.mileage_km)}</div>
            <div>{p.transmission}</div>
            <div>{p.body_type}</div>
            <div>{p.condition}</div>
            <div>{p.fuel}</div>
            <div>📍 {p.location}</div>
          </dl>
        </div>
      </div>

      {status === "pending" || status === "publishing" ? (
        <div className="flex gap-2 px-4 pb-4">
          <button
            onClick={confirm}
            disabled={status === "publishing"}
            className="flex-1 rounded-lg bg-brand px-4 py-2 font-semibold text-ink transition hover:bg-brand-light disabled:opacity-60"
          >
            {status === "publishing" ? "Publishing…" : "Confirm & publish"}
          </button>
          <button
            onClick={cancel}
            disabled={status === "publishing"}
            className="rounded-lg border border-slate-200 px-4 py-2 font-medium text-slate-600 transition hover:bg-slate-50"
          >
            Cancel
          </button>
        </div>
      ) : (
        <p
          className={
            "mx-4 mb-4 rounded-lg px-3 py-2 text-sm " +
            (status === "published"
              ? "bg-emerald-50 text-emerald-700"
              : status === "cancelled"
                ? "bg-slate-100 text-slate-600"
                : "bg-red-50 text-red-600")
          }
        >
          {status === "cancelled" ? "Listing discarded." : message}
        </p>
      )}
    </div>
  );
}
