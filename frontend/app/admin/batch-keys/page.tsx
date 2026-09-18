"use client";

import { useState, type FormEvent } from "react";
import { Download, FileSpreadsheet, Loader2 } from "lucide-react";

import {
  downloadBatchKeysTemplate,
  exportBatchKeyRows,
  previewBatchKeys,
  submitBatchKeys,
  updateBatchKeys,
  type BatchCreateResult,
  type BatchKeyRow,
  type PreviewKeyRow,
  type PreviewKeysResult,
} from "@/lib/adminApi";
import { AdminGuard } from "@/components/AdminGuard";
import { useAuth } from "@/components/AuthProvider";
import { TeamPicker } from "@/components/TeamPicker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const ENVIRONMENTS = ["DEV", "STG", "PROD"] as const;

const INPUT_EXAMPLE = `email,name,key_alias,team,environment
ali.veli@allianz.com.tr,Ali Veli,,GENAI,DEV
ayse.yilmaz@allianz.com.tr,Ayşe Yılmaz,,HASAR,DEV`;

const COLUMNS: { name: string; required: boolean; note: string }[] = [
  { name: "email", required: true, note: "eposta, talep_eden_eposta" },
  { name: "name", required: false, note: "ad, ad_soyad — yoksa email local part" },
  { name: "key_alias", required: false, note: "alias — boşsa otomatik üretilir" },
  { name: "team", required: false, note: "takım adı — LiteLLM'de yoksa otomatik oluşturulur" },
  { name: "environment", required: false, note: "ortam — yoksa formdaki varsayılan" },
];

function EnvironmentSelect({
  id,
  value,
  onChange,
  disabled,
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <select
      id={id}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        "disabled:cursor-not-allowed disabled:opacity-50",
      )}
    >
      {ENVIRONMENTS.map((env) => (
        <option key={env} value={env}>
          {env}
        </option>
      ))}
    </select>
  );
}

function CsvSample({ label, sample }: { label: string; sample: string }) {
  return (
    <div className="grid gap-1.5">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <pre className="overflow-x-auto rounded-md border bg-muted/50 p-3 font-mono text-xs leading-5">
        {sample}
      </pre>
    </div>
  );
}

function FormatCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Dosya formatı (oluştur)</CardTitle>
        <CardDescription>
          Yükleme <code className="font-mono">.xlsx</code> veya{" "}
          <code className="font-mono">.csv</code> olabilir (ilk sayfa/satır başlık).
          Sonuç ekranda liste olarak gösterilir; indirmek istersen CSV veya Excel
          seçebilirsin.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-3">Kolon</th>
                <th className="py-2 pr-3">Zorunlu</th>
                <th className="py-2">Eşdeğer / not</th>
              </tr>
            </thead>
            <tbody>
              {COLUMNS.map((col) => (
                <tr key={col.name} className="border-b last:border-0">
                  <td className="py-2 pr-3 font-mono text-xs">{col.name}</td>
                  <td className="py-2 pr-3">
                    <Badge variant={col.required ? "default" : "secondary"}>
                      {col.required ? "zorunlu" : "opsiyonel"}
                    </Badge>
                  </td>
                  <td className="py-2 text-muted-foreground">{col.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <CsvSample label="Girdi örneği" sample={INPUT_EXAMPLE} />
        <p className="text-xs text-muted-foreground">
          Ayırıcı virgül. En fazla 200 satır. Model adı ve max parallel request
          formdan gelir; dosyada bu kolonlar gerekmez.{" "}
          <code className="font-mono">team</code> LiteLLM&apos;de yoksa otomatik
          oluşturulur (rastgele metin yerine gerçek bir LiteLLM team).
        </p>
      </CardContent>
    </Card>
  );
}

function UpdateFormatCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Dosya formatı (güncelle)</CardTitle>
        <CardDescription>
          Create çıktısı <code className="font-mono">.csv</code> veya{" "}
          <code className="font-mono">.xlsx</code>. Lookup{" "}
          <code className="font-mono">api_key</code>; ekranda email ve alias.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5">
        <p className="text-xs text-muted-foreground">
          Zorunlu kolon: api_key. Email görüntü. Ortam formdan (hangi LiteLLM).
          Boş form alanı key&apos;de değişmez. Takım seçimi dropdown&apos;dan
          gerçek LiteLLM team&apos;idir — serbest metin kabul edilmez.
        </p>
      </CardContent>
    </Card>
  );
}

function ApiKeyCell({ value }: { value: string }) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  return (
    <div className="flex items-center gap-1.5">
      <code className="max-w-[220px] truncate font-mono text-xs" title={value}>
        {value}
      </code>
      <button
        type="button"
        className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
        onClick={() => navigator.clipboard?.writeText(value).catch(() => undefined)}
      >
        kopyala
      </button>
    </div>
  );
}

function CreateResultsPanel({
  environment,
  result,
  onResultChange,
}: {
  environment: string;
  result: BatchCreateResult;
  onResultChange: (result: BatchCreateResult) => void;
}) {
  const selectableRows = result.rows.filter((row) => row.ok && row.api_key);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [teamId, setTeamId] = useState("");
  const [moving, setMoving] = useState(false);
  const [moveError, setMoveError] = useState<string | null>(null);
  const [moveDone, setMoveDone] = useState<{ succeeded: number; failed: number } | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<"csv" | "xlsx" | null>(null);

  const allSelected = selectableRows.length > 0 && selectableRows.every((r) => selected.has(r.row));
  const someSelected = selected.size > 0;

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(selectableRows.map((r) => r.row)));
  }

  function toggleRow(rowNumber: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(rowNumber)) next.delete(rowNumber);
      else next.add(rowNumber);
      return next;
    });
  }

  function targetRows(): BatchKeyRow[] {
    if (selected.size === 0) return selectableRows;
    return selectableRows.filter((r) => selected.has(r.row));
  }

  async function handleExport(format: "csv" | "xlsx") {
    setExporting(format);
    setExportError(null);
    try {
      await exportBatchKeyRows({
        format,
        filename: "orion-batch-keys",
        rows: targetRows().map((row) => ({
          email: row.email,
          name: row.name,
          key_alias: row.key_alias,
          team: row.team,
          environment: row.environment,
          api_key: row.api_key,
          status: row.ok ? "ok" : "error",
          error: row.error,
        })),
      });
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Dışa aktarılamadı");
    } finally {
      setExporting(null);
    }
  }

  async function handleMoveToTeam() {
    const rows = targetRows();
    if (!teamId || rows.length === 0) return;
    setMoving(true);
    setMoveError(null);
    setMoveDone(null);
    try {
      const outcome = await updateBatchKeys({
        environment,
        team: teamId,
        keys: rows.map((row) => ({
          api_key: row.api_key,
          email: row.email,
          key_alias: row.key_alias,
        })),
      });
      setMoveDone({ succeeded: outcome.succeeded, failed: outcome.failed });
      const updatedEmails = new Set(
        outcome.rows.filter((r) => r.status === "updated").map((r) => r.email),
      );
      onResultChange({
        ...result,
        rows: result.rows.map((row) =>
          updatedEmails.has(row.email) ? { ...row, team: teamId } : row,
        ),
      });
    } catch (err) {
      setMoveError(err instanceof Error ? err.message : "Takıma taşınamadı");
    } finally {
      setMoving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Üretilen key&apos;ler</CardTitle>
        <CardDescription>
          {result.total} satır · {result.succeeded} başarılı · {result.failed} hata
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="max-h-[420px] overflow-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-background">
              <tr className="border-b text-left text-muted-foreground">
                <th className="w-8 py-2 pl-3">
                  <Checkbox
                    checked={allSelected ? true : someSelected ? "indeterminate" : false}
                    onCheckedChange={toggleAll}
                    disabled={selectableRows.length === 0}
                    aria-label="Tümünü seç"
                  />
                </th>
                <th className="py-2 pr-3">Email</th>
                <th className="py-2 pr-3">Alias</th>
                <th className="py-2 pr-3">Takım</th>
                <th className="py-2 pr-3">Ortam</th>
                <th className="py-2 pr-3">API key</th>
                <th className="py-2">Durum</th>
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row) => (
                <tr key={`${row.row}-${row.email}`} className="border-b last:border-0">
                  <td className="py-2 pl-3">
                    <Checkbox
                      checked={selected.has(row.row)}
                      onCheckedChange={() => toggleRow(row.row)}
                      disabled={!row.ok || !row.api_key}
                      aria-label={`${row.email} seç`}
                    />
                  </td>
                  <td className="py-2 pr-3">{row.email || "—"}</td>
                  <td className="py-2 pr-3 font-mono text-xs">{row.key_alias || "—"}</td>
                  <td className="py-2 pr-3">{row.team || "—"}</td>
                  <td className="py-2 pr-3">{row.environment || "—"}</td>
                  <td className="py-2 pr-3">
                    <ApiKeyCell value={row.api_key} />
                  </td>
                  <td className="py-2">
                    <Badge variant={row.ok ? "success" : "destructive"}>
                      {row.ok ? "başarılı" : "hata"}
                    </Badge>
                    {row.error ? (
                      <span className="mt-1 block max-w-[220px] text-xs text-destructive">
                        {row.error}
                      </span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={result.rows.length === 0 || exporting !== null}
            onClick={() => handleExport("csv")}
          >
            {exporting === "csv" ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Download className="size-4" />
            )}
            CSV indir {someSelected ? `(${selected.size} seçili)` : "(tümü)"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={result.rows.length === 0 || exporting !== null}
            onClick={() => handleExport("xlsx")}
          >
            {exporting === "xlsx" ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Download className="size-4" />
            )}
            Excel indir {someSelected ? `(${selected.size} seçili)` : "(tümü)"}
          </Button>
          {exportError && <p className="text-sm text-destructive">{exportError}</p>}
        </div>

        <div className="grid gap-2 rounded-md border bg-muted/20 p-3">
          <p className="text-sm font-medium">Seçilenleri bir takıma taşı</p>
          <TeamPicker environment={environment} value={teamId} onChange={setTeamId} />
          <Button
            type="button"
            size="sm"
            className="w-fit"
            disabled={!teamId || moving || selectableRows.length === 0}
            onClick={handleMoveToTeam}
          >
            {moving && <Loader2 className="size-4 animate-spin" />}
            {someSelected ? `${selected.size} key'i` : `Tüm ${selectableRows.length} key'i`} takıma taşı
          </Button>
          {moveDone && (
            <p className="text-sm text-muted-foreground">
              {moveDone.succeeded} güncellendi, {moveDone.failed} hata.
            </p>
          )}
          {moveError && <p className="text-sm text-destructive">{moveError}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

function CreatePanel() {
  const [file, setFile] = useState<File | null>(null);
  const [modelName, setModelName] = useState("");
  const [environment, setEnvironment] = useState("DEV");
  const [maxParallel, setMaxParallel] = useState("");
  const [sendMail, setSendMail] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BatchCreateResult | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file || !modelName.trim()) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const outcome = await submitBatchKeys({
        file,
        modelName: modelName.trim(),
        sendMail,
        environment,
        maxParallelRequests: maxParallel.trim(),
      });
      setResult(outcome);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Batch başarısız");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid gap-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,28rem)_minmax(0,1fr)] lg:items-start">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileSpreadsheet className="size-5" /> Excel/CSV ile toplu LiteLLM key
            </CardTitle>
            <CardDescription>
              Satır başına LiteLLM virtual key üretir. Sonuç ekranda liste
              olarak görünür; istersen CSV veya Excel indirebilirsin.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4" onSubmit={handleSubmit}>
              <div className="grid gap-1.5">
                <Label htmlFor="batch-file">Dosya (.xlsx veya .csv)</Label>
                <Input
                  id="batch-file"
                  type="file"
                  accept=".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="model-name">Model adı</Label>
                <Input
                  id="model-name"
                  value={modelName}
                  onChange={(event) => setModelName(event.target.value)}
                  placeholder="allianz-text"
                  required
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="environment">Varsayılan ortam</Label>
                <EnvironmentSelect id="environment" value={environment} onChange={setEnvironment} />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="max-parallel">Max parallel request</Label>
                <Input
                  id="max-parallel"
                  type="number"
                  min={1}
                  value={maxParallel}
                  onChange={(event) => setMaxParallel(event.target.value)}
                  placeholder="boş = limitsiz"
                />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={sendMail}
                  onCheckedChange={(value) => setSendMail(value === true)}
                />
                Sonuç maili gönder
              </label>
              <div className="flex flex-wrap gap-2">
                <Button type="submit" disabled={!file || !modelName.trim() || submitting}>
                  {submitting && <Loader2 className="size-4 animate-spin" />}
                  {submitting ? "İşleniyor..." : "Key'leri üret"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    downloadBatchKeysTemplate().catch((err: unknown) => {
                      setError(err instanceof Error ? err.message : "Şablon indirilemedi");
                    });
                  }}
                >
                  <Download className="size-4" /> Şablon indir
                </Button>
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
            </form>
          </CardContent>
        </Card>
        <FormatCard />
      </div>
      {result && (
        <CreateResultsPanel environment={result.environment} result={result} onResultChange={setResult} />
      )}
    </div>
  );
}

function splitModels(raw: string): string[] {
  return raw
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function UpdatePanel() {
  const [file, setFile] = useState<File | null>(null);
  const [environment, setEnvironment] = useState("DEV");
  const [previewing, setPreviewing] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewKeysResult | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [teamId, setTeamId] = useState("");
  const [maxParallel, setMaxParallel] = useState("");
  const [models, setModels] = useState("");
  const [blocked, setBlocked] = useState(false);
  const [clearMetadata, setClearMetadata] = useState(false);
  const [stripRowCount, setStripRowCount] = useState(false);
  const [resolveTeamPerRow, setResolveTeamPerRow] = useState(false);
  const [updateResult, setUpdateResult] = useState<{
    total: number;
    succeeded: number;
    failed: number;
    rows: { email: string; key_alias: string; team: string; status: string; error: string }[];
  } | null>(null);

  const foundRows = preview?.rows.filter((row: PreviewKeyRow) => row.found) ?? [];
  const allSelected = foundRows.length > 0 && foundRows.every((row) => selected.has(row.row));
  const someSelected = selected.size > 0;
  const selectedRows = someSelected ? foundRows.filter((row) => selected.has(row.row)) : foundRows;
  const canUpdate =
    selectedRows.length > 0 &&
    (Boolean(teamId.trim()) ||
      Boolean(maxParallel.trim()) ||
      splitModels(models).length > 0 ||
      blocked ||
      clearMetadata ||
      stripRowCount ||
      resolveTeamPerRow);

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(foundRows.map((row) => row.row)));
  }

  function toggleRow(rowNumber: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(rowNumber)) next.delete(rowNumber);
      else next.add(rowNumber);
      return next;
    });
  }

  async function handlePreview(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setPreviewing(true);
    setError(null);
    setUpdateResult(null);
    setPreview(null);
    setSelected(new Set());
    try {
      const result = await previewBatchKeys({
        file,
        environment,
      });
      setPreview(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Önizleme başarısız");
    } finally {
      setPreviewing(false);
    }
  }

  async function handleUpdate(event: FormEvent) {
    event.preventDefault();
    if (!preview || !canUpdate) return;
    const parallelRaw = maxParallel.trim();
    const parallel = parallelRaw ? Number(parallelRaw) : null;
    if (parallelRaw && (!Number.isInteger(parallel) || (parallel ?? 0) < 1)) {
      setError("Max parallel en az 1 olmalı");
      return;
    }
    setUpdating(true);
    setError(null);
    setUpdateResult(null);
    try {
      const outcome = await updateBatchKeys({
        environment: preview.environment || environment,
        team: teamId.trim() || undefined,
        maxParallelRequests: parallel,
        models: splitModels(models),
        blocked,
        clearMetadata,
        stripRowCount,
        resolveTeamPerRow,
        keys: selectedRows.map((row) => ({
          api_key: row.api_key,
          email: row.email,
          key_alias: row.key_alias,
          team: row.team,
        })),
      });
      setUpdateResult(outcome);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Güncelleme başarısız");
    } finally {
      setUpdating(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,32rem)_minmax(0,1fr)] lg:items-start">
      <div className="grid gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Önizleme</CardTitle>
            <CardDescription>
              Create çıktısını (.csv veya .xlsx) yükle. LiteLLM&apos;de{" "}
              <code className="font-mono">api_key</code> ile bakılır; email ve
              alias gösterilir.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4" onSubmit={handlePreview}>
              <div className="grid gap-1.5">
                <Label htmlFor="update-env">Ortam</Label>
                <EnvironmentSelect id="update-env" value={environment} onChange={setEnvironment} />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="update-file">Dosya (.csv veya .xlsx)</Label>
                <Input
                  id="update-file"
                  type="file"
                  accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  onChange={(event) => {
                    setFile(event.target.files?.[0] ?? null);
                    setPreview(null);
                    setUpdateResult(null);
                    setSelected(new Set());
                  }}
                />
              </div>
              <Button type="submit" disabled={!file || previewing}>
                {previewing && <Loader2 className="size-4 animate-spin" />}
                {previewing ? "Bakılıyor..." : "Önizle"}
              </Button>
            </form>
          </CardContent>
        </Card>

        {preview && (
          <Card>
            <CardHeader>
              <CardTitle>Bulunan key&apos;ler</CardTitle>
              <CardDescription>
                {preview.csv_rows} satır · {preview.with_api_key} api_key ·{" "}
                {preview.found} bulundu · {preview.missing} yok — seçmezsen
                bulunan hepsi işleme girer.
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="w-8 py-2 pl-1">
                      <Checkbox
                        checked={allSelected ? true : someSelected ? "indeterminate" : false}
                        onCheckedChange={toggleAll}
                        disabled={foundRows.length === 0}
                        aria-label="Tümünü seç"
                      />
                    </th>
                    <th className="py-2 pr-3">Email</th>
                    <th className="py-2 pr-3">Alias</th>
                    <th className="py-2 pr-3">Takım</th>
                    <th className="py-2 pr-3">Modeller</th>
                    <th className="py-2 pr-3">Paralel</th>
                    <th className="py-2">Durum</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row) => (
                    <tr key={`${row.row}-${row.email}`} className="border-b last:border-0">
                      <td className="py-2 pl-1">
                        <Checkbox
                          checked={selected.has(row.row)}
                          onCheckedChange={() => toggleRow(row.row)}
                          disabled={!row.found}
                          aria-label={`${row.email} seç`}
                        />
                      </td>
                      <td className="py-2 pr-3">{row.email || "—"}</td>
                      <td className="py-2 pr-3 font-mono text-xs">{row.key_alias || "—"}</td>
                      <td className="py-2 pr-3">{row.team || "—"}</td>
                      <td className="py-2 pr-3">{row.models.join(", ") || "—"}</td>
                      <td className="py-2 pr-3 tabular-nums">
                        {row.max_parallel_requests ?? "—"}
                      </td>
                      <td className="py-2">
                        <Badge variant={row.found ? "success" : "destructive"}>
                          {row.found ? "bulundu" : "yok"}
                        </Badge>
                        {row.error ? (
                          <span className="mt-1 block text-xs text-destructive">{row.error}</span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}

        {preview && (
          <Card>
            <CardHeader>
              <CardTitle>Güncelle</CardTitle>
              <CardDescription>
                {someSelected ? `${selected.size} seçili` : `Tümü — bulunan ${foundRows.length} key`}.
                Boş alan değişmez.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form className="grid gap-4" onSubmit={handleUpdate}>
                <div className="grid gap-1.5">
                  <Label>Takım (tüm seçililere aynı takım)</Label>
                  <TeamPicker
                    environment={preview.environment || environment}
                    value={teamId}
                    onChange={setTeamId}
                    disabled={resolveTeamPerRow}
                  />
                </div>
                <label className="flex items-start gap-2 text-sm">
                  <Checkbox
                    checked={resolveTeamPerRow}
                    onCheckedChange={(value) => setResolveTeamPerRow(value === true)}
                    disabled={Boolean(teamId.trim())}
                  />
                  <span>
                    Takımı satırdaki değerden çöz/oluştur — her key&apos;in LiteLLM&apos;de
                    kayıtlı mevcut (eski akıştan kalma, doğrulanmamış string olabilir)
                    takım değeri LiteLLM&apos;deki gerçek takımlarla eşleştirilir; eşleşme
                    yoksa o isimle gerçek bir takım <strong>oluşturulur</strong>. Üstteki
                    Takım alanı doluysa bu yoksayılır.
                  </span>
                </label>
                <div className="grid gap-1.5">
                  <Label htmlFor="upd-parallel">Max parallel request</Label>
                  <Input
                    id="upd-parallel"
                    type="number"
                    min={1}
                    value={maxParallel}
                    onChange={(event) => setMaxParallel(event.target.value)}
                    placeholder="boş = dokunma"
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="upd-models">Modeller</Label>
                  <Input
                    id="upd-models"
                    value={models}
                    onChange={(event) => setModels(event.target.value)}
                    placeholder="allianz-text, allianz-vision"
                  />
                  <p className="text-xs text-muted-foreground">Virgülle ayır. Boş = dokunma.</p>
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={blocked}
                    onCheckedChange={(value) => setBlocked(value === true)}
                  />
                  Key&apos;leri blokla
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={clearMetadata}
                    onCheckedChange={(value) => setClearMetadata(value === true)}
                  />
                  Metadata&apos;yı temizle (batch/talep kaynaklı eski bilgileri sil)
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={stripRowCount}
                    onCheckedChange={(value) => setStripRowCount(value === true)}
                  />
                  Alias&apos;daki satır numarasını kaldır (ör. ALIVELI2 → ALIVELI)
                </label>
                <Button type="submit" disabled={!canUpdate || updating}>
                  {updating && <Loader2 className="size-4 animate-spin" />}
                  {updating ? "Güncelleniyor..." : "Güncelle"}
                </Button>
              </form>
              {updateResult && (
                <div className="mt-4 grid gap-2 rounded-md border bg-muted/20 p-3">
                  <p className="text-sm">
                    {updateResult.succeeded} güncellendi, {updateResult.failed} hata
                    ({updateResult.total} toplam).
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        exportBatchKeyRows({
                          format: "csv",
                          filename: "orion-batch-keys-update",
                          rows: updateResult.rows,
                        }).catch((err: unknown) => {
                          setError(err instanceof Error ? err.message : "Dışa aktarılamadı");
                        })
                      }
                    >
                      <Download className="size-4" /> CSV indir
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        exportBatchKeyRows({
                          format: "xlsx",
                          filename: "orion-batch-keys-update",
                          rows: updateResult.rows,
                        }).catch((err: unknown) => {
                          setError(err instanceof Error ? err.message : "Dışa aktarılamadı");
                        })
                      }
                    >
                      <Download className="size-4" /> Excel indir
                    </Button>
                  </div>
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b text-xs text-muted-foreground">
                        <th className="py-1 pr-3 font-medium">Email</th>
                        <th className="py-1 pr-3 font-medium">Alias</th>
                        <th className="py-1 pr-3 font-medium">Takım</th>
                        <th className="py-1 font-medium">Durum</th>
                      </tr>
                    </thead>
                    <tbody>
                      {updateResult.rows.map((row) => (
                        <tr key={`${row.email}-${row.key_alias}`} className="border-b last:border-0">
                          <td className="py-1.5 pr-3">{row.email || "—"}</td>
                          <td className="py-1.5 pr-3 font-mono text-xs">{row.key_alias || "—"}</td>
                          <td className="py-1.5 pr-3 font-mono text-xs">{row.team || "—"}</td>
                          <td className="py-1.5">
                            <Badge
                              variant={
                                row.status === "updated"
                                  ? "success"
                                  : row.status === "error"
                                    ? "destructive"
                                    : "secondary"
                              }
                            >
                              {row.status}
                            </Badge>
                            {row.error ? (
                              <span className="mt-1 block text-xs text-destructive">{row.error}</span>
                            ) : null}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>
      <UpdateFormatCard />
    </div>
  );
}

function BatchKeysContent() {
  const { user } = useAuth();
  const [mode, setMode] = useState<"create" | "update">("create");

  if (!user?.is_superuser) {
    return <p className="text-sm text-muted-foreground">Bu sayfa yalnız superuser içindir.</p>;
  }

  return (
    <div className="grid gap-6">
      <div className="flex gap-2">
        <Button
          type="button"
          variant={mode === "create" ? "default" : "outline"}
          onClick={() => setMode("create")}
        >
          Oluştur
        </Button>
        <Button
          type="button"
          variant={mode === "update" ? "default" : "outline"}
          onClick={() => setMode("update")}
        >
          Güncelle
        </Button>
      </div>
      {mode === "create" ? <CreatePanel /> : <UpdatePanel />}
    </div>
  );
}

export default function BatchKeysPage() {
  return (
    <AdminGuard>
      <BatchKeysContent />
    </AdminGuard>
  );
}
