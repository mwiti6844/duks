"use client";

import type { DemoUser, UIAction } from "@/lib/types";
import BrandMark from "@/components/BrandMark";

const JOURNEYS = [
  {
    icon: "⌕",
    title: "Buy a car",
    description: "Find vehicles that match your budget and needs.",
    message: "Help me buy a car",
    action: { type: "start_journey", journey: "buy_car" },
  },
  {
    icon: "＋",
    title: "Sell a car",
    description: "Create and publish a listing through a guided conversation.",
    message: "I want to sell my car",
    action: { type: "start_journey", journey: "sell_car" },
  },
  {
    icon: "◫",
    title: "Finance a car",
    description: "Explore deposits, terms, and estimated monthly payments.",
    message: "Help me finance a car",
    action: { type: "start_journey", journey: "finance_car" },
  },
  {
    icon: "⇄",
    title: "Trade in",
    description: "Learn how to value and trade in your current vehicle.",
    message: "Tell me about trading in my car",
    action: { type: "start_journey", journey: "trade_in" },
  },
  {
    icon: "◇",
    title: "Insure a car",
    description: "Understand available vehicle insurance options.",
    message: "Tell me about vehicle insurance",
    action: { type: "start_journey", journey: "insurance" },
  },
  {
    icon: "▦",
    title: "Dealer finance",
    description: "Learn about stock financing for motor dealerships.",
    message: "Tell me about dealership financing",
    action: { type: "start_journey", journey: "dealer_finance" },
  },
] satisfies Array<{
  icon: string;
  title: string;
  description: string;
  message: string;
  action: UIAction;
}>;

export default function EmptyChatState({
  onAction,
  disabled,
  user,
}: {
  onAction: (message: string, action: UIAction) => void;
  disabled: boolean;
  user?: DemoUser | null;
}) {
  const firstName = user?.full_name?.trim().split(/\s+/)[0];

  return (
    <div className="flex min-h-full items-center justify-center py-10">
      <div className="w-full max-w-3xl text-center">
        <div className="flex justify-center"><BrandMark /></div>
        <p className="mt-4 text-sm font-medium text-muted">
          {firstName ? `Welcome back, ${firstName}` : "Welcome to CarDuka"}
        </p>
        <h2 className="mt-1 text-xl font-semibold text-ink">
          What would you like to do today?
        </h2>
        <p className="mx-auto mt-2 max-w-xl text-sm text-muted">
          {user?.location
            ? `Your CarDuka assistant is ready to help from ${user.location}—choose a journey or ask your own question.`
            : "Choose a journey or ask your own question below."}
        </p>

        <div className="mt-7 grid grid-cols-1 gap-3 text-left sm:grid-cols-2 lg:grid-cols-3">
          {JOURNEYS.map((journey) => (
            <button
              key={journey.title}
              type="button"
              disabled={disabled}
              onClick={() => onAction(journey.message, journey.action)}
              className="group rounded-2xl border border-card-border bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-brand hover:shadow-md disabled:pointer-events-none disabled:opacity-50"
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand/25 text-lg font-semibold text-ink">
                {journey.icon}
              </span>
              <span className="mt-4 block text-sm font-semibold text-ink">{journey.title}</span>
              <span className="mt-1 block text-xs leading-5 text-muted">
                {journey.description}
              </span>
              <span className="mt-4 block text-right text-lg text-slate-300 transition group-hover:text-ink">
                →
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
