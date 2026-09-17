"use client";

import { useState, type FormEvent } from "react";
import { Download, FileSpreadsheet, Loader2 } from "lucide-react";

import {
  downloadBatchKeysTemplate,
  previewBatchKeys,
  submitBatchKeys,
  updateBatchKeys,
  type PreviewKeysResult,
} from "@/lib/adminApi";
import { AdminGuard } from "@/components/AdminGuard";
import { useAuth } from "@/components/AuthProvider";
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

const INPUT_EXAMPLE = `email,name,key_alias,team,environment
ali.veli@allianz.com.tr,Ali Veli,,GENAI,DEV
ayse.yilmaz@allianz.com.tr,Ayşe Yılmaz,,HASAR,DEV`;

const OUTPUT_EXAMPLE = `email,name,key_alias,team,environment,api_key
ali.veli@allianz.com.tr,Ali Veli,ALZ-GENAI-ALIVELI2-DEV-ALLIANZ-TEXT,GENAI,DEV,sk-...
ayse.yilmaz@allianz.com.tr,Ayşe Yılmaz,ALZ-HASAR-AYSEYILMAZ3-DEV-ALLIANZ-TEXT,HASAR,DEV,sk-...`;

const COLUMNS: { name: string; required: boolean; note: string }[] = [
  { name: "email", required: true, note: "eposta, talep_eden_eposta" },
  { name: "name", required: false, note: "ad, ad_soyad — yoksa email local part" },
  { name: "key_alias", required: false, note: "alias — boşsa otomatik üretilir" },
  { name: "team", required: false, note: "departman, litellm_team_id" },
  { name: "environment", required: false, note: "ortam — yoksa formdaki varsayılan" },
];

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
        <CardTitle>CSV formatı (oluştur)</CardTitle>
        <CardDescription>
          Yükleme .xlsx (ilk sayfa, ilk satır başlık). Cevap UTF-8 CSV; mevcut
          kolonlar korunur, sona <code className="font-mono">api_key</code> eklenir.
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
              <tr>
                <td className="py-2 pr-3 font-mono text-xs">api_key</td>
                <td className="py-2 pr-3">
                  <Badge variant="success">çıktı</Badge>
                </td>
                <td className="py-2 text-muted-foreground">
                  Endpoint yazar. Hata satırında boş kalır. Güncelleme bu CSV’yi alır.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <CsvSample label="Girdi örneği" sample={INPUT_EXAMPLE} />
        <CsvSample label="Dönen CSV" sample={OUTPUT_EXAMPLE} />
        <p className="text-xs text-muted-foreground">
          Ayırıcı virgül. En fazla 200 satır. Model adı ve max parallel request
          formdan gelir; Excel’de bu kolonlar gerekmez.
        </p>
      </CardContent>
    </Card>
  );
}

function UpdateFormatCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>CSV formatı (güncelle)</CardTitle>
        <CardDescription>
          Create çıktısı CSV. Lookup <code className="font-mono">api_key</code>;
          ekranda email ve alias.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5">
        <CsvSample label="Girdi (create output)" sample={OUTPUT_EXAMPLE} />
        <p className="text-xs text-muted-foreground">
          Zorunlu kolon: api_key. Email görüntü. Ortam formdan (hangi LiteLLM).
          Boş form alanı key’de değişmez. Blokla işaretlenirse blocked=true.
        </p>
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
  const [done, setDone] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file || !modelName.trim()) return;
    setSubmitting(true);
    setError(null);
    setDone(false);
    try {
      await submitBatchKeys({
        file,
        modelName: modelName.trim(),
        sendMail,
        environment: environment.trim() || "DEV",
        maxParallelRequests: maxParallel.trim(),
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Batch başarısız");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,28rem)_minmax(0,1fr)] lg:items-start">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileSpreadsheet className="size-5" /> Excel ile toplu LiteLLM key
          </CardTitle>
          <CardDescription>
            Satır başına LiteLLM virtual key üretir. Cevap, aynı satırlara
            <code className="mx-1 font-mono">api_key</code> basılmış CSV’dir.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4" onSubmit={handleSubmit}>
            <div className="grid gap-1.5">
              <Label htmlFor="batch-file">Excel (.xlsx)</Label>
              <Input
                id="batch-file"
                type="file"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
              <Input
                id="environment"
                value={environment}
                onChange={(event) => setEnvironment(event.target.value)}
                placeholder="DEV"
              />
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
                {submitting ? "İşleniyor..." : "CSV indir"}
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
            {done && !error && (
              <p className="text-sm text-muted-foreground">
                CSV indirildi (<code className="font-mono">api_key</code> kolonu eklendi).
              </p>
            )}
          </form>
        </CardContent>
      </Card>
      <FormatCard />
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
  const [team, setTeam] = useState("");
  const [maxParallel, setMaxParallel] = useState("");
  const [models, setModels] = useState("");
  const [blocked, setBlocked] = useState(false);
  const [done, setDone] = useState(false);

  const foundRows = preview?.rows.filter((row) => row.found) ?? [];
  const canUpdate =
    foundRows.length > 0 &&
    (Boolean(team.trim()) ||
      Boolean(maxParallel.trim()) ||
      splitModels(models).length > 0 ||
      blocked);

  async function handlePreview(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setPreviewing(true);
    setError(null);
    setDone(false);
    setPreview(null);
    try {
      const result = await previewBatchKeys({
        file,
        environment: environment.trim() || "DEV",
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
    setDone(false);
    try {
      await updateBatchKeys({
        environment: preview.environment || environment.trim() || "DEV",
        team: team.trim() || undefined,
        maxParallelRequests: parallel,
        models: splitModels(models),
        blocked,
        keys: foundRows.map((row) => ({
          api_key: row.api_key,
          email: row.email,
          key_alias: row.key_alias,
        })),
      });
      setDone(true);
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
            <CardTitle>CSV önizleme</CardTitle>
            <CardDescription>
              Create çıktısını yükle. LiteLLM’de <code className="font-mono">api_key</code>{" "}
              ile bakılır; email ve alias gösterilir.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4" onSubmit={handlePreview}>
              <div className="grid gap-1.5">
                <Label htmlFor="update-env">Ortam</Label>
                <Input
                  id="update-env"
                  value={environment}
                  onChange={(event) => setEnvironment(event.target.value)}
                  placeholder="DEV"
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="update-csv">CSV</Label>
                <Input
                  id="update-csv"
                  type="file"
                  accept=".csv,text/csv"
                  onChange={(event) => {
                    setFile(event.target.files?.[0] ?? null);
                    setPreview(null);
                    setDone(false);
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
              <CardTitle>Bulunan key’ler</CardTitle>
              <CardDescription>
                {preview.csv_rows} satır · {preview.with_api_key} api_key ·{" "}
                {preview.found} bulundu · {preview.missing} yok
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
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
                Yalnız bulunan {foundRows.length} key. Boş alan değişmez.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form className="grid gap-4" onSubmit={handleUpdate}>
                <div className="grid gap-1.5">
                  <Label htmlFor="upd-team">Takım adı</Label>
                  <Input
                    id="upd-team"
                    value={team}
                    onChange={(event) => setTeam(event.target.value)}
                    placeholder="boş = dokunma"
                  />
                </div>
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
                  Key’leri blokla
                </label>
                <Button type="submit" disabled={!canUpdate || updating}>
                  {updating && <Loader2 className="size-4 animate-spin" />}
                  {updating ? "Güncelleniyor..." : "Güncelle ve CSV indir"}
                </Button>
                {done && !error && (
                  <p className="text-sm text-muted-foreground">Güncelleme CSV indirildi.</p>
                )}
              </form>
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
