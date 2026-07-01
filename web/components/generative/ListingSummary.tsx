"use client";

import { useState } from "react";

import { kes, km } from "@/lib/format";

import CarImage from "./CarImage";
import ListingPhotoUploader from "./ListingPhotoUploader";
import ListingPriceGuidance from "./ListingPriceGuidance";
import ListingPublishReceipt from "./ListingPublishReceipt";

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
  description: string;
  signed_draft: Record<string, unknown>;
  revision: number;
  status: string;
  progress: number;
  validation: Array<{ field: string; level: "error" | "warning"; message: string }>;
  guidance: Record<string, unknown>;
  images: Array<{ id: string; secure_url: string }>;
  mode: "create" | "edit";
  restored?: boolean;
  action_status?: "published";
  receipt?: { listing_id: string; created: boolean; operation: "create" | "edit" };
}

type Status = "pending" | "publishing" | "published" | "cancelled" | "error";

export default function ListingSummary(p: Props) {
  const [status, setStatus] = useState<Status>(
    p.action_status === "published" ? "published" : "pending",
  );
  const [message, setMessage] = useState(
    p.action_status === "published" ? "This listing has already been published." : "",
  );
  const [editing, setEditing] = useState(false);
  const [data, setData] = useState(p);
  const [receipt, setReceipt] = useState<{ id: string; created: boolean } | null>(
    p.receipt ? { id: p.receipt.listing_id, created: p.receipt.created } : null,
  );

  const sessionId =
    typeof window !== "undefined" ? localStorage.getItem("carduka_sid") || "" : "";

  async function confirm() {
    setStatus("publishing");
    try {
      const res = await fetch("/api/listings/confirm", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ signed_draft: data.signed_draft, session_id: sessionId }),
      });
      const responseData = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(responseData?.detail || "Could not publish the listing");
      setStatus("published");
      setReceipt({ id: responseData.listing.id, created: responseData.created });
      setMessage(
        responseData.created
          ? `Your listing is live on CarDuka. Listing ID: ${responseData.listing.id}`
          : `This listing was already published. Listing ID: ${responseData.listing.id}`,
      );
    } catch (e) {
      setStatus("error");
      setMessage(e instanceof Error ? e.message : "Publish failed");
    }
  }

  async function refreshReview() {
    const res = await fetch(`/api/listing-drafts/${data.draft_id}/review`, { method: "POST" });
    const next = await res.json();
    if (!res.ok) throw new Error(next?.detail || "Could not refresh review");
    setData((current) => ({ ...current, ...next, ...(next.fields || {}) }));
  }

  async function saveEdits(form: FormData) {
    const fields: Record<string, string | number> = {};
    for (const key of ["make", "model", "year", "mileage_km", "price_kes", "transmission", "fuel", "condition", "body_type", "location", "description"]) {
      const value = String(form.get(key) || "").trim();
      fields[key] = ["year", "mileage_km", "price_kes"].includes(key) ? Number(value.replaceAll(",", "")) : value;
    }
    const patched = await fetch(`/api/listing-drafts/${data.draft_id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json", "x-session-id": sessionId },
      body: JSON.stringify({ fields }),
    });
    if (!patched.ok) throw new Error("Could not save listing changes");
    await refreshReview();
    setEditing(false);
  }

  async function polishDescription() {
    const res = await fetch(`/api/listing-drafts/${data.draft_id}/description/polish`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ facts: data.description }),
    });
    const result = await res.json();
    if (!res.ok) { setMessage(result.detail || "Could not polish description"); return; }
    setData((current) => ({ ...current, description: result.polished }));
    setEditing(true);
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
        <CarImage make={data.make} model={data.model} image_url={data.images[0]?.secure_url || data.image_url} className="h-28" />
        <div>
          <p className="text-lg font-semibold text-ink">
            {data.year} {data.make} {data.model}
          </p>
          <p className="text-xl font-bold text-ink">{kes(data.price_kes)}</p>
          <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-600">
            <div>{km(data.mileage_km)}</div>
            <div>{data.transmission}</div>
            <div>{data.body_type}</div>
            <div>{data.condition}</div>
            <div>{data.fuel}</div>
            <div>📍 {data.location}</div>
          </dl>
        </div>
      </div>
      <div className="space-y-3 px-4 pb-4">
        <p className="text-sm text-muted">{data.description}</p>
        <ListingPriceGuidance guidance={data.guidance} />
        {data.validation.map((issue) => (
          <p key={`${issue.field}-${issue.message}`} className={issue.level === "error" ? "text-xs text-red-600" : "text-xs text-amber-700"}>
            {issue.message}
          </p>
        ))}
        <ListingPhotoUploader draftId={data.draft_id} images={data.images} onChanged={refreshReview} />
      </div>

      {editing && (
        <form action={saveEdits} className="grid grid-cols-2 gap-2 border-t border-card-border p-4">
          {(["make", "model", "year", "mileage_km", "price_kes", "transmission", "fuel", "condition", "body_type", "location"] as const).map((key) => (
            <label key={key} className="text-xs text-muted">{key.replaceAll("_", " ")}
              <input name={key} defaultValue={String(data[key])} className="mt-1 w-full rounded border border-card-border px-2 py-1.5 text-ink" />
            </label>
          ))}
          <label className="col-span-2 text-xs text-muted">description
            <textarea name="description" defaultValue={data.description} className="mt-1 min-h-24 w-full rounded border border-card-border px-2 py-1.5 text-ink" />
          </label>
          <div className="col-span-2 flex gap-2">
            <button className="rounded bg-brand px-3 py-2 text-xs font-semibold text-ink">Save changes</button>
            <button type="button" onClick={() => setEditing(false)} className="rounded border border-card-border px-3 py-2 text-xs">Close</button>
          </div>
        </form>
      )}

      {status === "pending" || status === "publishing" ? (
        <div className="flex flex-wrap gap-2 px-4 pb-4">
          <button
            onClick={confirm}
            disabled={status === "publishing"}
            className="flex-1 rounded-lg bg-brand px-4 py-2 font-semibold text-ink transition hover:bg-brand-light disabled:opacity-60"
          >
            {status === "publishing" ? "Publishing…" : "Confirm & publish"}
          </button>
          <button onClick={() => setEditing(true)} className="rounded-lg border border-card-border px-4 py-2 text-sm">Edit</button>
          <button onClick={polishDescription} className="rounded-lg border border-card-border px-4 py-2 text-sm">Polish description</button>
          <button onClick={() => { window.location.href = "/my-listings"; }} className="rounded-lg border border-card-border px-4 py-2 text-sm">Save & exit</button>
          <button
            onClick={cancel}
            disabled={status === "publishing"}
            className="rounded-lg border border-slate-200 px-4 py-2 font-medium text-slate-600 transition hover:bg-slate-50"
          >
            Cancel
          </button>
        </div>
      ) : (
        receipt ? <div className="mx-4 mb-4"><ListingPublishReceipt listingId={receipt.id} created={receipt.created} operation={data.mode} /></div> : <p
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
