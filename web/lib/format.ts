export function kes(amount: number | null | undefined): string {
  if (amount == null) return "—";
  return "KES " + amount.toLocaleString("en-KE");
}

export function km(value: number): string {
  return value.toLocaleString("en-KE") + " km";
}

export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}
