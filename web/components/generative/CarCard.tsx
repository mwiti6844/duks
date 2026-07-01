import { kes, km } from "@/lib/format";
import type { UIAction } from "@/lib/types";

import CarImage from "./CarImage";

export interface CarProps {
  id: string;
  make: string;
  model: string;
  year: number;
  price_kes: number;
  mileage_km: number;
  transmission: string;
  fuel: string;
  location: string;
  condition: string;
  body_type: string;
  image_url?: string;
  description?: string | null;
  trim?: string | null;
  color?: string | null;
  engine_cc?: number | null;
  monthly_payment_kes?: number | null;
  finance_term_months?: number | null;
  source_url?: string | null;
  image_urls?: string[];
}

export default function CarCard({
  car,
  onAction,
}: {
  car: CarProps;
  onAction?: (label: string, action: UIAction) => void;
}) {
  const label = `Tell me more about the ${car.year} ${car.make} ${car.model}`;
  const content = (
    <>
      <div className="p-3">
        <CarImage make={car.make} model={car.model} image_url={car.image_url} />
      </div>
      <div className="px-4 pb-4">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="font-semibold text-ink">
            {car.year} {car.make} {car.model}{car.trim ? ` ${car.trim}` : ""}
          </h3>
          <span className="rounded-full bg-brand/25 px-2 py-0.5 text-xs font-medium text-ink">
            {car.condition}
          </span>
        </div>
        <p className="mt-1 text-lg font-bold text-ink">{kes(car.price_kes)}</p>
        {car.monthly_payment_kes ? (
          <p className="text-xs font-medium text-slate-500">
            from {kes(car.monthly_payment_kes)}/mo
          </p>
        ) : null}
        <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-600">
          <div>{km(car.mileage_km)}</div>
          <div>{car.transmission}</div>
          <div>{car.fuel}</div>
          {car.engine_cc ? <div>{car.engine_cc.toLocaleString()} cc</div> : null}
          <div>{car.body_type}</div>
          {car.color ? <div>{car.color}</div> : null}
          <div>📍 {car.location}</div>
        </dl>
        {car.description && (
          <p className="mt-2 line-clamp-2 text-xs text-slate-500">{car.description}</p>
        )}
      </div>
    </>
  );

  if (onAction) {
    return (
      <button
        type="button"
        aria-label={label}
        onClick={() => onAction(label, { type: "select_car", entity_id: car.id })}
        className="w-full overflow-hidden rounded-xl border border-card-border bg-white text-left shadow-sm transition hover:-translate-y-0.5 hover:border-brand hover:shadow-md focus:outline-none focus:ring-2 focus:ring-brand"
      >
        {content}
      </button>
    );
  }
  return (
    <div className="w-full overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition hover:shadow-md">
      {content}
    </div>
  );
}

export function CarCardList({
  cars,
  onAction,
}: {
  cars: CarProps[];
  onAction?: (label: string, action: UIAction) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
      {cars.map((c) => (
        <CarCard key={c.id} car={c} onAction={onAction} />
      ))}
    </div>
  );
}
