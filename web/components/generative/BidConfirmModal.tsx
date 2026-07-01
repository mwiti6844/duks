"use client";

import { useState } from "react";

import { kes } from "@/lib/format";

import type { AuctionProps } from "./AuctionCountdown";

interface Props {
  auction?: AuctionProps;
  amount_kes: number;
  meets_reserve?: boolean;
  signed_proposal: Record<string, unknown>;
  restored?: boolean;
  action_status?: "confirmed" | "expired";
  receipt?: Record<string, unknown>;
}

type Status = "pending" | "placing" | "placed" | "cancelled" | "error";

export default function BidConfirmModal(p: Props) {
  const [status, setStatus] = useState<Status>(
    p.action_status === "confirmed" ? "placed" : p.action_status === "expired" ? "error" : "pending",
  );
  const [message, setMessage] = useState<string>(
    p.action_status === "confirmed"
      ? "This bid has already been confirmed."
      : p.action_status === "expired"
        ? "This bid proposal has expired. Ask me to prepare a new bid."
        : "",
  );

  const sessionId =
    typeof window !== "undefined" ? localStorage.getItem("carduka_sid") || "" : "";

  async function confirm() {
    setStatus("placing");
    try {
      const res = await fetch("/api/bids/confirm", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ signed_proposal: p.signed_proposal, session_id: sessionId }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.detail || "Bid could not be placed");
      setStatus("placed");
      setMessage(
        data.meets_reserve
          ? "Bid placed — you're above the reserve price! 🎉"
          : "Bid placed. You're the highest bidder so far.",
      );
    } catch (e) {
      setStatus("error");
      setMessage(e instanceof Error ? e.message : "Bid failed");
    }
  }

  async function cancel() {
    setStatus("cancelled");
    try {
      await fetch("/api/bids/cancel", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch {
      /* best effort */
    }
  }

  const title = p.auction
    ? `${p.auction.year} ${p.auction.make} ${p.auction.model}`
    : "Auction bid";

  return (
    <div className="rounded-xl border-2 border-accent/40 bg-white p-4 shadow-md">
      <div className="flex items-center gap-2">
        <span className="text-lg">🔨</span>
        <h3 className="font-semibold text-ink">Confirm your bid</h3>
        {p.restored && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
            restored
          </span>
        )}
      </div>

      <div className="mt-3 rounded-lg bg-slate-50 p-3">
        <p className="text-sm text-slate-500">{title}</p>
        <p className="text-2xl font-bold text-accent">{kes(p.amount_kes)}</p>
        {p.meets_reserve !== undefined && (
          <p className="mt-1 text-xs text-slate-500">
            {p.meets_reserve ? "✅ Meets the reserve price" : "Below reserve — still a valid bid"}
          </p>
        )}
      </div>

      {status === "pending" || status === "placing" ? (
        <div className="mt-4 flex gap-2">
          <button
            onClick={confirm}
            disabled={status === "placing"}
            className="flex-1 rounded-lg bg-brand px-4 py-2 font-semibold text-ink transition hover:bg-brand-light disabled:opacity-60"
          >
            {status === "placing" ? "Placing…" : "Confirm bid"}
          </button>
          <button
            onClick={cancel}
            disabled={status === "placing"}
            className="rounded-lg border border-slate-200 px-4 py-2 font-medium text-slate-600 transition hover:bg-slate-50"
          >
            Cancel
          </button>
        </div>
      ) : (
        <p
          className={
            "mt-4 rounded-lg px-3 py-2 text-sm " +
            (status === "placed"
              ? "bg-emerald-50 text-emerald-700"
              : status === "cancelled"
                ? "bg-slate-100 text-slate-600"
                : "bg-red-50 text-red-600")
          }
        >
          {status === "cancelled" ? "Bid cancelled." : message}
        </p>
      )}
    </div>
  );
}
