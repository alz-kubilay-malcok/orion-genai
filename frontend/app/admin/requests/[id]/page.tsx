"use client";

import { use, useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";

import { getRequestDetail, type AdminRequestDetail } from "@/lib/adminApi";
import { AdminGuard } from "@/components/AdminGuard";
import { AdminRequestActions } from "@/components/AdminRequestActions";
import { RequestDetailPanel } from "@/components/RequestDetailPanel";
import { ResultBanner } from "@/components/ResultBanner";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  isSettledStatus,
  statusBadgeVariant,
  statusLabel,
} from "@/lib/requestStatus";

const REQUEST_TYPE_LABELS: Record<string, string> = {
  litellm_key: "LiteLLM API Anahtarı",
  mcp_key: "MCP Erişim Anahtarı",
  mcp_server_registry: "MCP Sunucu Kaydı",
};

function DetailContent({ requestId }: { requestId: string }) {
  const [detail, setDetail] = useState<AdminRequestDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getRequestDetail(requestId)
      .then(setDetail)
      .catch(() => setError("Talep yüklenemedi"));
  }, [requestId]);

  if (error) return <ResultBanner tone="error" title="Hata" message={error} />;
  if (!detail) return <p className="text-sm text-muted-foreground">Yükleniyor...</p>;

  return (
    <div className="flex w-full flex-col gap-6">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={() => history.back()}>
          ← Listeye dön
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => getRequestDetail(requestId).then(setDetail).catch(() => setError("Talep yüklenemedi"))}
        >
          Yenile
        </Button>
      </div>

      <Card>
        <CardHeader className="gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant={statusBadgeVariant(detail.status)}>
              {detail.status === "provisioning" ? "Onaylandı" : statusLabel(detail.status)}
            </Badge>
            <Badge variant="outline">{detail.environment}</Badge>
          </div>
          <CardTitle>
            {REQUEST_TYPE_LABELS[detail.request_type] ?? detail.request_type} —{" "}
            {detail.genai_orion_panel_ticket_id}
          </CardTitle>
          <CardDescription>
            {detail.requester_name} ({detail.requester_email}) ·{" "}
            {new Date(detail.created_at).toLocaleString("tr-TR")} ·{" "}
            <a
              href={detail.genai_orion_panel_ticket_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
            >
              Ticket <ExternalLink className="size-3.5" />
            </a>
          </CardDescription>
        </CardHeader>
        <CardContent>
          <RequestDetailPanel view={detail} />
        </CardContent>
      </Card>

      {isSettledStatus(detail.status) ? (
        <TerminalSummary detail={detail} />
      ) : (
        <AdminRequestActions
          detail={detail}
          onActionComplete={(status) => {
            // Server-authoritative yeni durumu öne çıkar, sonra arka planda refetch et.
            setDetail({ ...detail, status, available_actions: [] } as AdminRequestDetail);
            void getRequestDetail(requestId).then(setDetail);
          }}
        />
      )}
    </div>
  );
}

function TerminalSummary({ detail }: { detail: AdminRequestDetail }) {
  const detailRecord = (detail.detail ?? {}) as Record<string, unknown>;
  const rejectReason = pickString(detailRecord, "reject_reason", "admin_note");
  const assigneeEmail = pickString(detailRecord, "assignee_email");
  const completedAt = pickString(detailRecord, "completed_at");
  const errorMessage = pickString(detailRecord, "error_message");
  const isRejected = detail.status === "rejected";
  const isFailed = detail.status === "failed";
  const isCompleted = detail.status === "completed";
  const isApprovedPending = detail.status === "provisioning";
  const tone: "error" | "info" = isFailed || isRejected ? "error" : "info";
  const title = isRejected
    ? "Bu talep reddedildi"
    : isFailed
      ? "Bu talep başarısız"
      : isCompleted
        ? "Bu talep tamamlandı"
        : isApprovedPending
          ? "Talep onaylandı"
          : "Bu talep sonuçlandırılmış";
  const message = isApprovedPending
    ? "İşlem alındı. Anahtar hazır olunca talep edene mail gider."
    : `Durum: ${statusLabel(detail.status)}`;
  return (
    <>
      <ResultBanner
        tone={tone}
        title={title}
        message={message}
      />
      {(rejectReason || assigneeEmail || completedAt || errorMessage) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Sonuç özeti</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            {rejectReason && (
              <Row label={isRejected ? "Red gerekçesi" : "Not"} value={rejectReason} />
            )}
            {assigneeEmail && <Row label="Atanan kişi" value={assigneeEmail} />}
            {completedAt && (
              <Row
                label={isCompleted ? "Tamamlanma" : "Bitiş"}
                value={new Date(completedAt).toLocaleString("tr-TR")}
              />
            )}
            {errorMessage && <Row label="Hata" value={errorMessage} />}
          </CardContent>
        </Card>
      )}
      <Separator />
    </>
  );
}

function pickString(record: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const v = record[key];
    if (typeof v === "string" && v.length > 0) return v;
  }
  return null;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:justify-between">
      <span className="text-xs uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="text-foreground">{value}</span>
    </div>
  );
}

export default function AdminRequestDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <AdminGuard>
      <DetailContent requestId={id} />
    </AdminGuard>
  );
}
