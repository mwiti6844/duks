"use client";

import { useState } from "react";

import { kes, km } from "@/lib/format";

import CarImage from "./CarImage";
import type { CarProps } from "./CarCard";

interface Props {
  car: CarProps;
  facts: Record<string, Record<string, unknown>>;
  image_urls: string[];
}

const LABELS: Record<string, string> = {
  cash_price_kes: "Cash price",
  monthly_payment_kes: "Estimated monthly payment",
  term_months: "Finance term",
  mileage_km: "Mileage",
  engine_cc: "Engine capacity",
  body_type: "Body type",
  location_detail: "Viewing location",
  seller_display_name: "Seller",
  source_listing_id: "CarDuka listing ID",
  source_url: "Original listing",
  image_count: "Photos",
};

function displayValue(key: string, value: unknown) {
  if (key.endsWith("_kes") && typeof value === "number") return kes(value);
  if (key === "mileage_km" && typeof value === "number") return km(value);
  if (key === "engine_cc" && typeof value === "number") return `${value.toLocaleString()} CC`;
  if (key === "term_months" && typeof value === "number") return `${value} months`;
  if (key === "source_url" && typeof value === "string") {
    return (
      <a href={value} target="_blank" rel="noreferrer" className="text-blue-600 underline">
        View on CarDuka
      </a>
    );
  }
  if (Array.isArray(value)) {
    return (
      <div className="flex flex-wrap gap-1">
        {value.slice(0, 20).map((item) => (
          <span key={String(item)} className="rounded-full bg-brand/15 px-2 py-1 text-xs">
            {String(item)}
          </span>
        ))}
      </div>
    );
  }
  return String(value);
}

export default function VehicleDetail({ car, facts, image_urls }: Props) {
  const images = image_urls.length ? image_urls : car.image_url ? [car.image_url] : [];
  const [selected, setSelected] = useState(images[0] || "");
  const entries = Object.values(facts).flatMap((group) => Object.entries(group));

  return (
    <article className="overflow-hidden rounded-xl border border-card-border bg-white shadow-sm">
      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(360px,1.15fr)_minmax(320px,1fr)]">
        <div>
          <CarImage
            make={car.make}
            model={car.model}
            image_url={selected}
            className="h-72 lg:h-96"
          />
          {images.length > 1 && (
            <div className="scroll-thin mt-2 flex gap-2 overflow-x-auto pb-1">
              {images.map((url, index) => (
                <button
                  key={url}
                  type="button"
                  onClick={() => setSelected(url)}
                  className={`h-16 w-24 shrink-0 overflow-hidden rounded-lg border-2 ${
                    selected === url ? "border-brand" : "border-transparent"
                  }`}
                  aria-label={`View photo ${index + 1}`}
                >
                  {/* Source URLs are already normalized and allow-listed by ingestion. */}
                  <img src={url} alt="" className="h-full w-full object-cover" />
                </button>
              ))}
            </div>
          )}
        </div>

        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">
            CarDuka listing
          </p>
          <h3 className="mt-1 text-2xl font-bold text-ink">
            {car.year} {car.make} {car.model}{car.trim ? ` ${car.trim}` : ""}
          </h3>
          <p className="mt-1 text-2xl font-bold text-ink">{kes(car.price_kes)}</p>
          <dl className="mt-4 divide-y divide-card-border rounded-xl border border-card-border">
            {entries.map(([key, value]) => (
              <div key={key} className="grid gap-1 px-3 py-2 text-sm sm:grid-cols-[150px_1fr]">
                <dt className="text-muted">{LABELS[key] || key.replaceAll("_", " ")}</dt>
                <dd className="font-medium text-ink">{displayValue(key, value)}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </article>
  );
}
