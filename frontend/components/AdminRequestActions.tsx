"use client";

import { useState } from "react";
import { Loader2, ShieldCheck, PencilLine, ShieldX } from "lucide-react";

import type { AdminRequestDetail } from "@/lib/adminApi";
import { adminApprove, adminReject, adminRevise } from "@/lib/adminApi";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { ResultBanner } from "@/components/ResultBanner";

type Props = {
  detail: AdminRequestDetail;
  onActionComplete?: (status: string) => void;
};

type Mode = "approve" | "revise" | "reject" | null;
type SubmitState =
  | { phase: "idle" }
  | { phase: "submitting" }
  | { phase: "success"; status: string }
  | { phase: "error"; message: string };

export function AdminRequestActions({ detail, onActionComplete }: Props) {
  // Hook'lar daima çagrilir (Rules of Hooks); erken return en sonda yapilir.
  // `available_actions` bos ise veya talep `waiting_approval` degilse islem
  // panelini gostermeyelim — ALREADY_PROCESSED gibi durumlar onay akisini
  // kapatir, iskelet ekrana gelmesin.
  const [mode, setMode] = useState<Mode>(null);
  const [state, setState] = useState<SubmitState>({ phase: "idle" });

  const [allowsAllTools, setAllowsAllTools] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const detailRecord = (detail.detail ?? {}) as Record<string, unknown>;
  const [teamId, setTeamId] = useState(
    typeof detailRecord.litellm_team_id === "string" && detailRecord.litellm_team_id
      ? detailRecord.litellm_team_id
      : typeof detailRecord.department_name === "string"
        ? detailRecord.department_name
        : "",
  );
  const [maxParallel, setMaxParallel] = useState(
    typeof detailRecord.max_concurrent_requests === "number"
      ? String(detailRecord.max_concurrent_requests)
      : typeof detailRecord.max_concurrent_requests === "string"
        ? detailRecord.max_concurrent_requests
        : "1",
  );
  const [adminNote, setAdminNote] = useState("");

  // Client-facing fields (litellm_key only). Existing değerleri initial state'e kopyala
  // ki admin değiştirmediğinde dokunulmamış gibi görünsün; sıfırlamak için checkbox.
  const [modelsRaw, setModelsRaw] = useState<string>(
    Array.isArray(detailRecord.models)
      ? detailRecord.models.map((m) => String(m)).join(", ")
      : "",
  );
  const [responseWindow, setResponseWindow] = useState<string>(
    typeof detailRecord.response_window === "string" ? detailRecord.response_window : "",
  );
  const [usageFrequency, setUsageFrequency] = useState<string>(
    typeof detailRecord.usage_frequency === "string" ? detailRecord.usage_frequency : "",
  );
  const [enableClientFacing, setEnableClientFacing] = useState(false);

  const submitting = state.phase === "submitting";

  function reset() {
    setState({ phase: "idle" });
    setMode(null);
    setTeamId(
      typeof detailRecord.litellm_team_id === "string" && detailRecord.litellm_team_id
        ? detailRecord.litellm_team_id
        : typeof detailRecord.department_name === "string"
          ? detailRecord.department_name
          : "",
    );
    setMaxParallel(
      typeof detailRecord.max_concurrent_requests === "number"
        ? String(detailRecord.max_concurrent_requests)
        : typeof detailRecord.max_concurrent_requests === "string"
          ? detailRecord.max_concurrent_requests
          : "1",
    );
    setAdminNote("");
    setRejectReason("");
    setAllowsAllTools(false);
    setModelsRaw("");
    setResponseWindow("");
    setUsageFrequency("");
    setEnableClientFacing(false);
  }

  function switchMode(next: Mode) {
    // Mod değişirken önceki submit state'i temizle ki spinner sıkışmasın.
    setState({ phase: "idle" });
    setMode(next);
  }

  async function submitApprove() {
    setState({ phase: "submitting" });
    try {
      const result = await adminApprove(detail.request_id, {
        request_version: detail.request_version,
        allows_all_tools: detail.request_type === "mcp_server_registry" ? allowsAllTools : null,
      });
      if (result.ok) {
        setState({ phase: "success", status: result.status });
        onActionComplete?.(result.status);
      } else {
        setState({ phase: "error", message: result.errorCode });
      }
    } catch (err) {
      setState({ phase: "error", message: err instanceof Error ? err.message : "UNKNOWN_ERROR" });
    }
  }

  async function submitRevise() {
    const team = teamId.trim();
    const parallel = Number(maxParallel);
    if (!team) {
      setState({ phase: "error", message: "LiteLLM team adı zorunlu" });
      return;
    }
    if (!Number.isFinite(parallel) || parallel < 1) {
      setState({ phase: "error", message: "Anlık paralel istek en az 1 olmalı" });
      return;
    }
    // Client-facing düzeltmeleri sadece admin bilinçli açtıysa gönder.
    // Boş bırakılmış alanlar "alanı sıfırla" olarak yorumlanır — mevcut değer kontrolsüz silinmesin.
    const models = enableClientFacing
      ? modelsRaw
          .split(",")
          .map((m) => m.trim())
          .filter((m) => m.length > 0)
      : null;
    const response_window = enableClientFacing ? (responseWindow.trim() || null) : null;
    const usage_frequency = enableClientFacing ? (usageFrequency.trim() || null) : null;

    setState({ phase: "submitting" });
    try {
      const result = await adminRevise(detail.request_id, {
        request_version: detail.request_version,
        team_id: team,
        max_parallel_requests: parallel,
        admin_note: adminNote || undefined,
        models,
        response_window,
        usage_frequency,
      });
      if (result.ok) {
        setState({ phase: "success", status: result.status });
        onActionComplete?.(result.status);
      } else {
        setState({ phase: "error", message: result.errorCode });
      }
    } catch (err) {
      setState({ phase: "error", message: err instanceof Error ? err.message : "UNKNOWN_ERROR" });
    }
  }

  async function submitReject() {
    if (rejectReason.trim().length === 0) {
      setState({ phase: "error", message: "Red gerekçesi zorunlu" });
      return;
    }
    setState({ phase: "submitting" });
    try {
      const result = await adminReject(detail.request_id, {
        request_version: detail.request_version,
        reject_reason: rejectReason.trim(),
      });
      if (result.ok) {
        setState({ phase: "success", status: result.status });
        onActionComplete?.(result.status);
      } else {
        setState({ phase: "error", message: result.errorCode });
      }
    } catch (err) {
      setState({ phase: "error", message: err instanceof Error ? err.message : "UNKNOWN_ERROR" });
    }
  }

  // Panel sadece `waiting_approval` statusunde ve `available_actions` bos
  // olmayan taleplere gosterilir. ALREADY_PROCESSED gibi onaylanamayacak
  // durumlarda form yerine sadece TerminalSummary satirinin durmasi yeterli.
  const hasActions =
    detail.status === "waiting_approval" && detail.available_actions.length > 0;
  if (!hasActions) {
    return null;
  }

  // Tek başarı/hata göstergesi yukarıda (submit phase'ine göre render edilir).
  // Aktif mod seçili değilse sadece Onayla/Revize/Reddet düğmeleri; mod seçiliyse form + submit butonu.
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">İşlem</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {state.phase === "success" ? (
          <ResultBanner
            tone="info"
            title="İşlem tamamlandı"
            message={`Yeni durum: ${state.status}`}
          />
        ) : state.phase === "error" ? (
          <ResultBanner tone="error" title="İşlem başarısız" message={state.message} />
        ) : null}

        <div className="flex flex-wrap gap-2">
          {detail.available_actions.includes("approve") && (
            <Button
              variant={mode === "approve" ? "default" : "outline"}
              onClick={() => switchMode("approve")}
              disabled={submitting}
            >
              <ShieldCheck className="size-4" /> Onayla
            </Button>
          )}
          {detail.available_actions.includes("revise") && (
            <Button
              variant={mode === "revise" ? "default" : "outline"}
              onClick={() => switchMode("revise")}
              disabled={submitting}
            >
              <PencilLine className="size-4" /> Revize
            </Button>
          )}
          {detail.available_actions.includes("reject") && (
            <Button
              variant={mode === "reject" ? "destructive" : "outline"}
              onClick={() => switchMode("reject")}
              disabled={submitting}
            >
              <ShieldX className="size-4" /> Reddet
            </Button>
          )}
        </div>

        {mode === "approve" && detail.request_type === "mcp_server_registry" && (
          <div className="flex items-center gap-2">
            <Checkbox
              id="allows-all-tools"
              checked={allowsAllTools}
              onCheckedChange={(v) => setAllowsAllTools(v === true)}
            />
            <Label htmlFor="allows-all-tools">Tüm araçlara erişime izin ver</Label>
          </div>
        )}

        {mode === "revise" && (
          <div className="flex flex-col gap-5">
            <div className="flex flex-col gap-3 rounded-md border border-border/60 bg-muted/20 p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                LiteLLM key limitleri
              </p>
              <p className="text-xs text-muted-foreground -mt-2">
                Team adı <code>team_id</code>; anlık paralel istek <code>max_parallel_requests</code>.
              </p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="team-id">LiteLLM team adı</Label>
                  <Input id="team-id" value={teamId} onChange={(e) => setTeamId(e.target.value)} maxLength={128} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="max-parallel">Anlık paralel istek</Label>
                  <Input id="max-parallel" type="number" min={1} value={maxParallel} onChange={(e) => setMaxParallel(e.target.value)} />
                </div>
                <div className="flex flex-col gap-1.5 sm:col-span-2">
                  <Label htmlFor="admin-note">Not (opsiyonel)</Label>
                  <Textarea id="admin-note" value={adminNote} onChange={(e) => setAdminNote(e.target.value)} maxLength={2000} />
                </div>
              </div>
            </div>

            {detail.request_type === "litellm_key" && (
              <div className="flex flex-col gap-3 rounded-md border border-border/60 p-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      Talep edilen bilgiler (istasyon mail'ine yansıyacak)
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Sadece burayı düzenlersen sistem talep edene diff içeren mail gönderir.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="enable-client-facing"
                      checked={enableClientFacing}
                      onCheckedChange={(v) => setEnableClientFacing(v === true)}
                    />
                    <Label htmlFor="enable-client-facing">Düzelt</Label>
                  </div>
                </div>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="flex flex-col gap-1.5 sm:col-span-2">
                    <Label htmlFor="models">Model listesi (virgülle)</Label>
                    <Input
                      id="models"
                      value={modelsRaw}
                      onChange={(e) => setModelsRaw(e.target.value)}
                      disabled={!enableClientFacing}
                      placeholder="örn. gpt-4o, gpt-3.5-turbo"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="response-window">Yanıt süresi</Label>
                    <Input
                      id="response-window"
                      value={responseWindow}
                      onChange={(e) => setResponseWindow(e.target.value)}
                      disabled={!enableClientFacing}
                      maxLength={64}
                      placeholder="örn. 24h"
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="usage-frequency">Kullanım sıklığı</Label>
                    <Input
                      id="usage-frequency"
                      value={usageFrequency}
                      onChange={(e) => setUsageFrequency(e.target.value)}
                      disabled={!enableClientFacing}
                      maxLength={64}
                      placeholder="örn. günlük"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {mode === "reject" && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="reject-reason">Red gerekçesi</Label>
            <Textarea
              id="reject-reason"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              maxLength={2000}
            />
          </div>
        )}
      </CardContent>

      {mode && (
        <CardFooter className="flex-col items-stretch gap-2">
          <Button
            variant={mode === "reject" ? "destructive" : "default"}
            disabled={submitting}
            onClick={mode === "approve" ? submitApprove : mode === "revise" ? submitRevise : submitReject}
          >
            {submitting && <Loader2 className="size-4 animate-spin" />}
            {mode === "approve" ? "Onayla" : mode === "revise" ? "Revize gönder" : "Reddet"}
          </Button>
          {state.phase === "success" && (
            <Button variant="outline" onClick={reset}>
              Kapat
            </Button>
          )}
        </CardFooter>
      )}
    </Card>
  );
}
