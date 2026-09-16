"use client";

import { useState, type FormEvent } from "react";
import { Download, FileSpreadsheet, Loader2 } from "lucide-react";

import {
  downloadBatchKeysTemplate,
  submitBatchKeys,
  type BatchKeysResult,
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

function copyText(value: string) {
  void navigator.clipboard.writeText(value);
}

function BatchKeysContent() {
  const { user } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [modelName, setModelName] = useState("");
  const [environment, setEnvironment] = useState("DEV");
  const [sendMail, setSendMail] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BatchKeysResult | null>(null);

  if (!user?.is_superuser) {
    return <p className="text-sm text-muted-foreground">Bu sayfa yalnız superuser içindir.</p>;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file || !modelName.trim()) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const payload = await submitBatchKeys({
        file,
        modelName: modelName.trim(),
        sendMail,
        environment: environment.trim() || "DEV",
      });
      setResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Batch başarısız");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileSpreadsheet className="size-5" /> Excel ile toplu LiteLLM key
          </CardTitle>
          <CardDescription>
            Excel satırlarından LiteLLM virtual key üretir. Model adı tüm satırlara
            uygulanır. Mail kutusu işaretliyse her başarılı key requester e-postasına gider.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid max-w-xl gap-4" onSubmit={handleSubmit}>
            <div className="grid gap-1.5">
              <Label htmlFor="batch-file">Excel (.xlsx)</Label>
              <Input
                id="batch-file"
                type="file"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <p className="text-xs text-muted-foreground">
                Zorunlu kolon: email. Opsiyonel: name, key_alias, team, environment.
              </p>
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
                {submitting ? "İşleniyor..." : "Key üret"}
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

      {result && (
        <Card>
          <CardHeader>
            <CardTitle>Sonuç</CardTitle>
            <CardDescription>
              {result.succeeded}/{result.total} başarılı
              {result.failed ? ` · ${result.failed} hata` : ""}
              {result.send_mail ? " · mail açık" : ""}
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-3">Satır</th>
                  <th className="py-2 pr-3">E-posta</th>
                  <th className="py-2 pr-3">Alias</th>
                  <th className="py-2 pr-3">Durum</th>
                  <th className="py-2 pr-3">Key</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((row) => (
                  <tr key={`${row.row}-${row.email}`} className="border-b last:border-0">
                    <td className="py-2 pr-3 tabular-nums">{row.row}</td>
                    <td className="py-2 pr-3">{row.email}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{row.key_alias}</td>
                    <td className="py-2 pr-3">
                      <Badge variant={row.ok ? "success" : "destructive"}>
                        {row.ok ? (row.mailed ? "ok + mail" : "ok") : "hata"}
                      </Badge>
                      {row.error ? (
                        <span className="mt-1 block text-xs text-destructive">{row.error}</span>
                      ) : null}
                    </td>
                    <td className="py-2 pr-3">
                      {row.api_key ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => copyText(row.api_key)}
                        >
                          Kopyala
                        </Button>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
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
