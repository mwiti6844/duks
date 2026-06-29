"use client";

import { useState } from "react";

// Renders the real listing image when one is provided, falling back to a branded
// gradient tile if the URL is empty or fails to load (real CDN URLs may hotlink-block
// or 404). Deterministic hue per make keeps the fallback pleasant.
const HUES: Record<string, string> = {
  Subaru: "from-blue-500 to-blue-700",
  Toyota: "from-red-500 to-rose-700",
  Nissan: "from-slate-500 to-slate-700",
  Lexus: "from-amber-500 to-orange-700",
  Suzuki: "from-emerald-500 to-emerald-700",
  Mazda: "from-indigo-500 to-indigo-700",
};

export default function CarImage({
  make,
  model,
  image_url,
  className = "h-32",
}: {
  make: string;
  model: string;
  image_url?: string;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const showImage = !!image_url && !failed;

  if (showImage) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={image_url}
        alt={`${make} ${model}`}
        onError={() => setFailed(true)}
        className={`w-full rounded-lg object-cover ${className}`}
      />
    );
  }

  const hue = HUES[make] ?? "from-soft-ink to-ink";
  return (
    <div
      className={`flex w-full items-center justify-center rounded-lg bg-gradient-to-br ${hue} ${className}`}
    >
      <div className="text-center text-white/95">
        <div className="text-3xl">🚗</div>
        <div className="mt-1 text-xs font-medium opacity-90">
          {make} {model}
        </div>
      </div>
    </div>
  );
}
