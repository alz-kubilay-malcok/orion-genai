/** Ortak durum haritalama: hem dashboard'da hem detay sayfasında paylaşılır. */

export type RequestStatus =
  | "received"
  | "waiting_approval"
  | "assigned"
  | "provisioning"
  | "completed"
  | "rejected"
  | "failed"
  | "expired"
  | (string & {}); // backend yeni durum eklediğinde TypeScript'in patlamasını engeller

export type BadgeVariant =
  | "default"
  | "secondary"
  | "destructive"
  | "outline"
  | "warning";

export const TERMINAL_STATUSES: ReadonlySet<RequestStatus> = new Set([
  "completed",
  "rejected",
  "failed",
  "expired",
]);

export const OPEN_STATUSES: ReadonlySet<RequestStatus> = new Set([
  "received",
  "waiting_approval",
  "assigned",
  "provisioning",
]);

export const REQUEST_STATUS_LABELS: Record<string, string> = {
  received: "Alındı",
  waiting_approval: "Onay bekliyor",
  assigned: "Atandı",
  provisioning: "Sağlanıyor",
  completed: "Tamamlandı",
  rejected: "Reddedildi",
  failed: "Başarısız",
  expired: "Süresi doldu",
};

export const REQUEST_STATUS_BADGE_VARIANT: Record<string, BadgeVariant> = {
  received: "outline",
  waiting_approval: "warning",
  assigned: "secondary",
  provisioning: "default",
  completed: "default",
  rejected: "destructive",
  failed: "destructive",
  expired: "outline",
};

export const REQUEST_STATUS_FILTER_OPTIONS: ReadonlyArray<{
  value: string;
  label: string;
}> = [
  { value: "open", label: "Açık (varsayılan)" },
  { value: "received", label: "Alındı" },
  { value: "waiting_approval", label: "Onay bekliyor" },
  { value: "assigned", label: "Atandı" },
  { value: "provisioning", label: "Sağlanıyor" },
  { value: "completed", label: "Tamamlandı" },
  { value: "rejected", label: "Reddedildi" },
  { value: "failed", label: "Başarısız" },
  { value: "expired", label: "Süresi doldu" },
  { value: "all", label: "Tümü" },
];

export function isTerminalStatus(status: RequestStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

export function isSettledStatus(status: RequestStatus): boolean {
  return isTerminalStatus(status) || status === "provisioning";
}

export function isOpenStatus(status: RequestStatus): boolean {
  return OPEN_STATUSES.has(status);
}

export function statusLabel(status: RequestStatus): string {
  return REQUEST_STATUS_LABELS[status] ?? status;
}

export function statusBadgeVariant(status: RequestStatus): BadgeVariant {
  return REQUEST_STATUS_BADGE_VARIANT[status] ?? "outline";
}
