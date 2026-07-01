"use client";

import { useEffect, useState } from "react";

import { kes, km } from "@/lib/format";
import type { UIAction } from "@/lib/types";

import CarImage from "./CarImage";

export interface AuctionProps {
  id: string;
  make: string;
  model: string;
  year: number;
  mileage_km: number;
  transmission: string;
  location: string;
  image_url?: string;
  current_bid_kes: number;
  min_increment_kes: number;
  min_next_bid_kes: number;
  ends_at: string;
}

function useCountdown(endsAt: string): string {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const ms = new Date(endsAt).getTime() - now;
  if (ms <= 0) return "Ended";
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (d > 0) return `${d}d ${h}h ${m}m`;
  return `${h}h ${m}m ${sec}s`;
}

function AuctionTile({
  a,
  onAction,
}: {
  a: AuctionProps;
  onAction?: (label: string, action: UIAction) => void;
}) {
  const remaining = useCountdown(a.ends_at);
  const ending = remaining !== "Ended" && !remaining.includes("d") && remaining.startsWith("0h");
  const content = (
    <>
      <div className="p-3">
        <CarImage make={a.make} model={a.model} image_url={a.image_url} className="h-28" />
      </div>
      <div className="px-4 pb-4">
        <h3 className="font-semibold text-ink">
          {a.year} {a.make} {a.model}
        </h3>
        <div className="mt-2 flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400">Current bid</p>
            <p className="font-bold text-ink">{kes(a.current_bid_kes)}</p>
          </div>
          <div
            className={
              "rounded-lg px-3 py-1.5 text-center " +
              (ending ? "bg-red-50 text-red-600" : "bg-slate-100 text-slate-700")
            }
          >
            <p className="text-[10px] uppercase tracking-wide opacity-70">Ends in</p>
            <p className="font-mono text-sm font-semibold tabular-nums">{remaining}</p>
          </div>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Min next bid {kes(a.min_next_bid_kes)} · {km(a.mileage_km)} · 📍 {a.location}
        </p>
      </div>
    </>
  );
  if (onAction) {
    const label = `Tell me more about the ${a.year} ${a.make} ${a.model} auction`;
    return (
      <button
        type="button"
        aria-label={label}
        onClick={() => onAction(label, { type: "select_auction", entity_id: a.id })}
        className="overflow-hidden rounded-xl border border-card-border bg-white text-left shadow-sm transition hover:-translate-y-0.5 hover:border-brand hover:shadow-md focus:outline-none focus:ring-2 focus:ring-brand"
      >
        {content}
      </button>
    );
  }
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      {content}
    </div>
  );
}

export default function AuctionCountdown({
  auctions,
  onAction,
}: {
  auctions: AuctionProps[];
  onAction?: (label: string, action: UIAction) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
      {auctions.map((a) => (
        <AuctionTile key={a.id} a={a} onAction={onAction} />
      ))}
    </div>
  );
}
