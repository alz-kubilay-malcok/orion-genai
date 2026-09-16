"use client";

import { useState, type FormEvent } from "react";
import { Download, FileSpreadsheet, Loader2 } from "lucide-react";

import { downloadBatchKeysTemplate, submitBatchKeys } from "@/lib/adminApi";
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
        <CardTitle>CSV formatı</CardTitle>
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
                  Endpoint yazar. Hata satırında boş kalır.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <CsvSample label="Girdi örneği" sample={INPUT_EXAMPLE} />
        <CsvSample label="Dönen CSV" sample={OUTPUT_EXAMPLE} />
        <p className="text-xs text-muted-foreground">
          Ayırıcı virgül. En fazla 200 satır. Model adı formdan gelir, Excel’de
          model kolonu gerekmez.
        </p>
      </CardContent>
    </Card>
  );
}

function BatchKeysContent() {
  const { user } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [modelName, setModelName] = useState("");
  const [environment, setEnvironment] = useState("DEV");
  const [sendMail, setSendMail] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  if (!user?.is_superuser) {
    return <p className="text-sm text-muted-foreground">Bu sayfa yalnız superuser içindir.</p>;
  }

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

export default function BatchKeysPage() {
  return (
    <AdminGuard>
      <BatchKeysContent />
    </AdminGuard>
  );
}
