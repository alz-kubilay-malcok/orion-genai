"use client";

import { useState } from "react";
import { Loader2, ShieldCheck, PencilLine, ShieldX } from "lucide-react";

import type { ApprovalViewModel } from "@/lib/actionSchema";
import { postApprove, postReject, postRevise } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { ResultBanner } from "@/components/ResultBanner";
import { LiteLLMTeamSelect } from "@/components/LiteLLMTeamSelect";

type Props = {
  token: string;
  view: ApprovalViewModel;
};

type SubmitState =
  | { phase: "idle" }
  | { phase: "submitting" }
  | { phase: "success"; status: string }
  | { phase: "error"; message: string };

export function ApprovalActions({ token, view }: Props) {
  const [state, setState] = useState<SubmitState>({ phase: "idle" });

  // reject reason
  const [rejectReason, setRejectReason] = useState("");

  const viewDetail = (view.detail ?? {}) as Record<string, unknown>;

  // revise fields (litellm_key only)
  const [teamId, setTeamId] = useState(
    typeof viewDetail.litellm_team_id === "string" && viewDetail.litellm_team_id
      ? viewDetail.litellm_team_id
      : typeof viewDetail.department_name === "string"
        ? viewDetail.department_name
        : "",
  );
  const [maxParallel, setMaxParallel] = useState(
    typeof viewDetail.max_concurrent_requests === "number"
      ? String(viewDetail.max_concurrent_requests)
      : typeof viewDetail.max_concurrent_requests === "string"
        ? viewDetail.max_concurrent_requests
        : "1",
  );
  const [adminNote, setAdminNote] = useState("");

  // Client-facing fields (litellm_key only). Backend'e sadece bilinçli
  // düzeltme yapıldığında gönderilir; aksi halde alana dokunulmaz.
  const [modelsRaw, setModelsRaw] = useState<string>(
    Array.isArray(viewDetail.models)
      ? viewDetail.models.map((m) => String(m)).join(", ")
      : "",
  );
  const [responseWindow, setResponseWindow] = useState<string>(
    typeof viewDetail.response_window === "string" ? viewDetail.response_window : "",
  );
  const [usageFrequency, setUsageFrequency] = useState<string>(
    typeof viewDetail.usage_frequency === "string" ? viewDetail.usage_frequency : "",
  );
  const [enableClientFacing, setEnableClientFacing] = useState(false);

  // approve — mcp_server_registry admin decision
  const [allowsAllTools, setAllowsAllTools] = useState(false);

  if (state.phase === "success") {
    const title =
      view.action === "reject"
        ? "Talep reddedildi"
        : view.action === "revise"
          ? "Revize kaydedildi"
          : "Talep onaylandı";
    const message =
      view.action === "reject"
        ? "Talep edene red gerekçesi iletilecek."
        : "İşlem alındı. Anahtar hazır olunca talep edene mail gider.";
    return <ResultBanner tone="info" title={title} message={message} />;
  }

  const submitting = state.phase === "submitting";

  async function handleApprove() {
    setState({ phase: "submitting" });
    try {
      const result = await postApprove({
        token,
        request_version: view.request_version,
        allows_all_tools: view.request_type === "mcp_server_registry" ? allowsAllTools : null,
      });
      setState(
        result.ok
          ? { phase: "success", status: result.data.status }
          : { phase: "error", message: result.errorCode },
      );
    } catch (err) {
      setState({ phase: "error", message: err instanceof Error ? err.message : "UNKNOWN_ERROR" });
    }
  }

  async function handleRevise() {
    const team = teamId.trim();
    const parallel = Number(maxParallel);
    if (!team) {
      setState({ phase: "error", message: "LiteLLM team seçin" });
      return;
    }
    if (!Number.isFinite(parallel) || parallel < 1) {
      setState({ phase: "error", message: "Anlık paralel istek en az 1 olmalı" });
      return;
    }
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
      const result = await postRevise({
        token,
        request_version: view.request_version,
        team_id: team,
        max_parallel_requests: parallel,
        admin_note: adminNote || undefined,
        models,
        response_window,
        usage_frequency,
      });
      setState(
        result.ok
          ? { phase: "success", status: result.data.status }
          : { phase: "error", message: result.errorCode },
      );
    } catch (err) {
      setState({ phase: "error", message: err instanceof Error ? err.message : "UNKNOWN_ERROR" });
    }
  }

  async function handleReject() {
    if (rejectReason.trim().length === 0) {
      setState({ phase: "error", message: "Red gerekçesi zorunlu" });
      return;
    }
    setState({ phase: "submitting" });
    try {
      const result = await postReject({
        token,
        request_version: view.request_version,
        reject_reason: rejectReason.trim(),
      });
      setState(
        result.ok
          ? { phase: "success", status: result.data.status }
          : { phase: "error", message: result.errorCode },
      );
    } catch (err) {
      setState({ phase: "error", message: err instanceof Error ? err.message : "UNKNOWN_ERROR" });
    }
  }

  return (
    <Card>
      {view.action === "approve" && (
        <>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="size-5 text-primary" /> Talebi onayla
            </CardTitle>
            <CardDescription>
              Onayladığınızda anahtar hazırlığı başlar; hazır olunca talep edene mail gider.
            </CardDescription>
          </CardHeader>
          {view.request_type === "mcp_server_registry" && (
            <CardContent>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="allows-all-tools"
                  checked={allowsAllTools}
                  onCheckedChange={(v) => setAllowsAllTools(v === true)}
                />
                <Label htmlFor="allows-all-tools">Tüm araçlara erişime izin ver</Label>
              </div>
            </CardContent>
          )}
          <CardFooter className="flex-col items-stretch gap-2">
            {state.phase === "error" && (
              <p className="text-sm text-destructive">{state.message}</p>
            )}
            <Button onClick={handleApprove} disabled={submitting}>
              {submitting && <Loader2 className="size-4 animate-spin" />}
              Onayla
            </Button>
          </CardFooter>
        </>
      )}

      {view.action === "revise" && (
        <>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <PencilLine className="size-5 text-amber-600" /> Talebi revize et
            </CardTitle>
            <CardDescription>
              Limitleri LiteLLM team ve anlık paralel istek olarak ayarlayabilirsiniz.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            <div className="flex flex-col gap-3 rounded-md border border-border/60 bg-muted/20 p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                LiteLLM key limitleri
              </p>
              <p className="text-xs text-muted-foreground -mt-2">
                Team LiteLLM listesinden seçilir; anlık paralel istek{" "}
                <code>max_parallel_requests</code> (eşzamanlı tavan, 429).
              </p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="team-id">LiteLLM team</Label>
                  <LiteLLMTeamSelect
                    id="team-id"
                    teams={view.litellm_teams ?? []}
                    value={teamId}
                    onChange={setTeamId}
                    disabled={submitting}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="max-parallel">Anlık paralel istek</Label>
                  <Input
                    id="max-parallel"
                    type="number"
                    min={1}
                    value={maxParallel}
                    onChange={(e) => setMaxParallel(e.target.value)}
                    placeholder="örn. 5"
                  />
                </div>
                <div className="flex flex-col gap-1.5 sm:col-span-2">
                  <Label htmlFor="admin-note">Not (opsiyonel)</Label>
                  <Textarea
                    id="admin-note"
                    value={adminNote}
                    onChange={(e) => setAdminNote(e.target.value)}
                    placeholder="Örn. Politika gereği sınırlandırıldı"
                    maxLength={2000}
                  />
                </div>
              </div>
            </div>

            {view.request_type === "litellm_key" && (
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
          </CardContent>
          <CardFooter className="flex-col items-stretch gap-2">
            {state.phase === "error" && (
              <p className="text-sm text-destructive">{state.message}</p>
            )}
            <Button onClick={handleRevise} disabled={submitting}>
              {submitting && <Loader2 className="size-4 animate-spin" />}
              Revize gönder
            </Button>
          </CardFooter>
        </>
      )}

      {view.action === "reject" && (
        <>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldX className="size-5 text-destructive" /> Talebi reddet
            </CardTitle>
            <CardDescription>Red gerekçesi talep edene iletilir.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="reject-reason">Red gerekçesi</Label>
              <Textarea
                id="reject-reason"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Reddetme nedenini yazın"
                maxLength={2000}
              />
            </div>
          </CardContent>
          <CardFooter className="flex-col items-stretch gap-2">
            {state.phase === "error" && (
              <p className="text-sm text-destructive">{state.message}</p>
            )}
            <Button variant="destructive" onClick={handleReject} disabled={submitting}>
              {submitting && <Loader2 className="size-4 animate-spin" />}
              Reddet
            </Button>
          </CardFooter>
        </>
      )}
    </Card>
  );
}
