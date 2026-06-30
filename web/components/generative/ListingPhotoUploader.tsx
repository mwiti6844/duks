"use client";

import { useState } from "react";

interface ImageItem { id: string; secure_url: string }

export default function ListingPhotoUploader({
  draftId,
  images,
  onChanged,
}: {
  draftId: string;
  images: ImageItem[];
  onChanged: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function upload(file?: File) {
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      setError("Use a JPEG, PNG or WebP image."); return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError("Photos must be 10 MB or smaller."); return;
    }
    setBusy(true); setError("");
    try {
      const sig = await fetch("/api/media/cloudinary/signature").then(async (r) => {
        if (!r.ok) throw new Error((await r.json()).detail || "Uploads are unavailable");
        return r.json();
      });
      const form = new FormData();
      form.set("file", file);
      form.set("api_key", sig.api_key);
      form.set("timestamp", String(sig.timestamp));
      form.set("folder", sig.folder);
      form.set("signature", sig.signature);
      const cloud = await fetch(
        `https://api.cloudinary.com/v1_1/${sig.cloud_name}/image/upload`,
        { method: "POST", body: form },
      ).then(async (r) => {
        if (!r.ok) throw new Error("Cloudinary rejected the photo");
        return r.json();
      });
      const registered = await fetch(`/api/listing-drafts/${draftId}/images`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          public_id: cloud.public_id,
          secure_url: cloud.secure_url,
          width: cloud.width,
          height: cloud.height,
          format: cloud.format,
          bytes: cloud.bytes,
        }),
      });
      if (!registered.ok) throw new Error((await registered.json()).detail || "Could not attach photo");
      await onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally { setBusy(false); }
  }

  async function remove(imageId: string) {
    setBusy(true);
    await fetch(`/api/listing-drafts/${draftId}/images/${imageId}`, { method: "DELETE" });
    await onChanged();
    setBusy(false);
  }

  async function move(imageId: string, direction: -1 | 1) {
    const index = images.findIndex((item) => item.id === imageId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= images.length) return;
    const ordered = images.map((item) => item.id);
    [ordered[index], ordered[target]] = [ordered[target], ordered[index]];
    setBusy(true);
    await fetch(`/api/listing-drafts/${draftId}/images/order`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ image_ids: ordered }),
    });
    await onChanged();
    setBusy(false);
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {images.map((image) => (
          <div key={image.id} className="relative">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={image.secure_url} alt="" className="h-20 w-28 rounded-lg object-cover" />
            <button onClick={() => remove(image.id)} className="absolute right-1 top-1 rounded bg-black/70 px-1.5 text-xs text-white">×</button>
            <div className="absolute bottom-1 left-1 flex gap-1">
              <button onClick={() => move(image.id, -1)} className="rounded bg-black/70 px-1.5 text-xs text-white">←</button>
              <button onClick={() => move(image.id, 1)} className="rounded bg-black/70 px-1.5 text-xs text-white">→</button>
            </div>
          </div>
        ))}
      </div>
      <label className="mt-2 inline-block cursor-pointer rounded-lg border border-card-border px-3 py-2 text-xs font-medium text-ink">
        {busy ? "Uploading…" : "Add photo"}
        <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" disabled={busy} onChange={(e) => upload(e.target.files?.[0])} />
      </label>
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}
