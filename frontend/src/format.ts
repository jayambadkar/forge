export function gbp(amount: number | null | undefined) {
  if (amount === null || amount === undefined) return "—";
  return new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(amount);
}

export function when(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16);
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function ageDays(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 0;
  return Math.max(0, Math.floor((Date.now() - date.getTime()) / 86400000));
}

export function openedOn(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10) || "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

export function openLabel(value: string) {
  if (!value) return "Open date not recorded";
  return `Opened ${openedOn(value)} · ${sla(ageDays(value))}`;
}

export function sla(days: number) {
  if (days <= 0) return "Opened today";
  if (days === 1) return "1 day open";
  return `${days.toLocaleString("en-GB")} days open`;
}

export function mailto(to: string, subject: string, body: string) {
  const address = to ? encodeURIComponent(to) : "";
  return `mailto:${address}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

export function labelFor(id: string) {
  return (
    {
      bank: "Retail bank",
      emoney: "E-money",
      investment: "Investment",
      payments_fx: "Payments & FX",
    }[id] ?? id
  );
}
