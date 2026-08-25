"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Inbox, RefreshCw, ListChecks, ShieldCheck, ShieldX, Filter, ChevronLeft, ChevronRight } from "lucide-react";

import { listRequests, type RequestSummary } from "@/lib/adminApi";
import { AdminGuard } from "@/components/AdminGuard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  REQUEST_STATUS_FILTER_OPTIONS,
  isOpenStatus,
  isTerminalStatus,
  statusBadgeVariant,
  statusLabel,
} from "@/lib/requestStatus";

/**
 * KPI kartının temsil ettiği filtre değeri.
 * - "open" → `isOpenStatus` setindeki tüm statüler (varsayılan dashboard).
 * - "completed" / "rejected" → belirli terminal statü.
 * - null ise kart salt sayaçtır, tıklama kilitli (henüz bu yapiya ihtiyacımız yok).
 */
type KpiFilter = "open" | "all" | RequestSummary["status"];

const REQUEST_TYPE_LABELS: Record<string, string> = {
  litellm_key: "LiteLLM API Anahtarı",
  mcp_key: "MCP Erişim Anahtarı",
  mcp_server_registry: "MCP Sunucu Kaydı",
};

const REFRESH_INTERVAL_MS = 10_000;

const PAGE_SIZE = 50;

type FilterValue = "open" | "all" | RequestSummary["status"];

function summarize(rows: RequestSummary[]) {
  let waiting = 0;
  let rejected = 0;
  let completed = 0;
  for (const r of rows) {
    if (r.status === "waiting_approval") waiting += 1;
    if (isTerminalStatus(r.status)) {
      if (r.status === "completed") completed += 1;
      if (r.status === "rejected") rejected += 1;
    }
  }
  return { waiting, rejected, completed, total: rows.length };
}

function matchesFilter(status: RequestSummary["status"], filter: FilterValue) {
  if (filter === "all") return true;
  if (filter === "open") return isOpenStatus(status);
  return status === filter;
}

function countOpenNonWaiting(rows: RequestSummary[]) {
  let n = 0;
  for (const r of rows) {
    if (r.status === "waiting_approval") continue;
    if (isOpenStatus(r.status)) n += 1;
  }
  return n;
}

function DashboardContent() {
  const [requests, setRequests] = useState<RequestSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterValue>("open");
  const [page, setPage] = useState(1);
  const [reloadKey, setReloadKey] = useState(0);

  // Polling: backend her 10 saniyede yeniden çekilir; tab değiştirilince temizlenir.
  useEffect(() => {
    let cancelled = false;
    const fetchOnce = () => {
      listRequests()
        .then((rows) => {
          if (!cancelled) {
            setRequests(rows);
            setError(null);
          }
        })
        .catch(() => {
          if (!cancelled) setError("Talepler yüklenemedi");
        });
    };
    fetchOnce();
    const id = setInterval(fetchOnce, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [reloadKey]);

  const filtered = useMemo(
    () => (requests ?? []).filter((r) => matchesFilter(r.status, filter)),
    [requests, filter],
  );

  // Filtre veya son veri değiştiğinde sayfayı başa sar.
  useEffect(() => {
    setPage(1);
  }, [filter, requests]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageStart = (safePage - 1) * PAGE_SIZE;
  const paginated = filtered.slice(pageStart, pageStart + PAGE_SIZE);

  const summary = useMemo(() => summarize(requests ?? []), [requests]);
  const waitingTotal = requests ? summary.waiting : null;
  const openNonWaiting = requests ? countOpenNonWaiting(requests ?? []) : null;
  const completedTotal = requests ? summary.completed : null;
  const rejectedTotal = requests ? summary.rejected : null;
  const loading = requests === null && !error;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold">Talepler</h1>
          <p className="text-sm text-muted-foreground">
            Webhook üzerinden gelen taleplerin onay ve işlem durumu burada izlenir.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <Filter className="size-4" />
            <select
              aria-label="Durum filtresi"
              value={filter}
              onChange={(e) => setFilter(e.target.value as FilterValue)}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              {REQUEST_STATUS_FILTER_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setReloadKey((k) => k + 1)}
            disabled={loading}
          >
            <RefreshCw className={`mr-1 size-4 ${loading ? "animate-spin" : ""}`} />
            Yenile
          </Button>
        </div>
      </header>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard
          label="Açık"
          value={waitingTotal !== null ? waitingTotal + (openNonWaiting ?? 0) : null}
          icon={<ListChecks className="size-4" />}
          filterValue="open"
          activeFilter={filter}
          onActivate={setFilter}
        />
        <KpiCard
          label="Onay bekliyor"
          value={waitingTotal}
          icon={<Inbox className="size-4" />}
          filterValue="waiting_approval"
          activeFilter={filter}
          onActivate={setFilter}
        />
        <KpiCard
          label="Tamamlandı"
          value={completedTotal}
          icon={<ShieldCheck className="size-4" />}
          filterValue="completed"
          activeFilter={filter}
          onActivate={setFilter}
        />
        <KpiCard
          label="Reddedildi"
          value={rejectedTotal}
          icon={<ShieldX className="size-4" />}
          filterValue="rejected"
          activeFilter={filter}
          onActivate={setFilter}
        />
      </section>

      {error && (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardContent className="py-4 text-sm text-destructive">{error}</CardContent>
        </Card>
      )}

      {loading ? (
        <DashboardSkeleton />
      ) : filtered.length === 0 ? (
        <EmptyState filter={filter} />
      ) : (
        <>
          <ul className="flex flex-col gap-3">
            {paginated.map((r) => (
              <li key={r.request_id}>
                <Link href={`/admin/requests/${r.request_id}`}>
                  <Card className="transition-colors hover:bg-accent">
                    <CardHeader className="gap-1">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <CardTitle className="text-base">
                          {REQUEST_TYPE_LABELS[r.request_type] ?? r.request_type} —{" "}
                          {r.genai_orion_panel_ticket_id}
                        </CardTitle>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Badge variant={statusBadgeVariant(r.status)}>{statusLabel(r.status)}</Badge>
                          {r.environment && <Badge variant="outline">{r.environment}</Badge>}
                        </div>
                      </div>
                      <CardDescription>
                        {r.requester_name} ({r.requester_email}) ·{" "}
                        {new Date(r.created_at).toLocaleString("tr-TR")}
                      </CardDescription>
                    </CardHeader>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
          <PaginationControls
            page={safePage}
            totalPages={totalPages}
            total={filtered.length}
            pageSize={PAGE_SIZE}
            onPrev={() => setPage((p) => Math.max(1, p - 1))}
            onNext={() => setPage((p) => Math.min(totalPages, p + 1))}
          />
        </>
      )}
    </div>
  );
}

function KpiCard({
  label,
  value,
  icon,
  filterValue,
  activeFilter,
  onActivate,
}: {
  label: string;
  value: number | null;
  icon: React.ReactNode;
  filterValue: KpiFilter | null;
  activeFilter: FilterValue;
  onActivate: (filter: KpiFilter) => void;
}) {
  // `filterValue === null` => kart salt sayac, tiklama kapali.
  // Aksi halde kart bir buton olarak davranir: aktif filtreyi vurgular,
  // basinca ddropdown'i da o filtreye cekip listeyi yeniler.
  const isInteractive = filterValue !== null;
  const isActive = filterValue !== null && activeFilter === filterValue;
  const interactiveClass = isInteractive
    ? "cursor-pointer transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    : "";
  const activeClass = isActive ? "border-primary bg-primary/5" : "";

  const body = (
    <Card className={`${interactiveClass} ${activeClass}`.trim()}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
          {isActive && (
            <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">
              filtre uygulandı
            </span>
          )}
        </CardTitle>
        <span className="text-muted-foreground">{icon}</span>
      </CardHeader>
      <CardContent>
        {value === null ? (
          <Skeleton className="h-7 w-12" />
        ) : (
          <p className="text-2xl font-semibold">{value}</p>
        )}
      </CardContent>
    </Card>
  );

  if (!isInteractive || !filterValue) {
    return body;
  }
  return (
    <button
      type="button"
      onClick={() => onActivate(filterValue)}
      aria-pressed={isActive}
      aria-label={`${label} filtresini uygula`}
      className="text-left"
    >
      {body}
    </button>
  );
}

function PaginationControls({
  page,
  totalPages,
  total,
  pageSize,
  onPrev,
  onNext,
}: {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  if (totalPages <= 1) {
    return (
      <p className="text-xs text-muted-foreground">
        Toplam {total} talep · sayfa başına {pageSize}
      </p>
    );
  }
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(total, page * pageSize);
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-xs text-muted-foreground">
        {first}-{last} arası gösteriliyor · toplam {total} · sayfa {page}/{totalPages}
      </p>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onPrev}
          disabled={page <= 1}
          aria-label="Önceki sayfa"
        >
          <ChevronLeft className="size-4" /> Önceki
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onNext}
          disabled={page >= totalPages}
          aria-label="Sonraki sayfa"
        >
          Sonraki <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <ul className="flex flex-col gap-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <li key={i}>
          <Card>
            <CardHeader className="gap-2">
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="h-4 w-1/2" />
            </CardHeader>
          </Card>
        </li>
      ))}
    </ul>
  );
}

function EmptyState({ filter }: { filter: FilterValue }) {
  const message =
    filter === "open"
      ? "Açık talep yok. Yeni geldiğinde burada görünecek."
      : filter === "all"
        ? "Henüz hiç talep yok."
        : `“${statusLabel(filter)}” durumunda talep yok.`;
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-2 py-10 text-center text-muted-foreground">
        <Inbox className="size-8" />
        <p>{message}</p>
      </CardContent>
    </Card>
  );
}

export default function AdminDashboardPage() {
  return (
    <AdminGuard>
      <DashboardContent />
    </AdminGuard>
  );
}
