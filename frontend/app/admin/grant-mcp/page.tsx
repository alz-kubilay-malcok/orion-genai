"use client";

import { useState, type FormEvent } from "react";
import { Loader2, Plug } from "lucide-react";

import { grantMcpAccess, type GrantMcpResult } from "@/lib/adminApi";
import { AdminGuard } from "@/components/AdminGuard";
import { useAuth } from "@/components/AuthProvider";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const ENVIRONMENTS = ["DEV", "TEST", "STG", "PROD"] as const;

const STATUS_LABEL: Record<GrantMcpResult["status"], string> = {
  granted: "Erişim verildi",
  already_granted: "Bu sunucu zaten tanımlıydı",
};

const MAIL_LABEL: Record<string, string> = {
  smtp_accepted: "Bilgilendirme maili gönderildi",
  recorded: "Mail SMTP’ye gitmedi; kayıt alındı",
  failed: "Erişim yazıldı, mail gönderilemedi",
};

function GrantContent() {
  const { user } = useAuth();
  const [keyAlias, setKeyAlias] = useState("");
  const [mcpName, setMcpName] = useState("");
  const [environment, setEnvironment] = useState<(typeof ENVIRONMENTS)[number]>("PROD");
  const [recipientEmail, setRecipientEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GrantMcpResult | null>(null);

  if (!user?.is_superuser) {
    return <p className="text-sm text-muted-foreground">Bu sayfa yalnız superuser içindir.</p>;
  }

  const canSubmit =
    keyAlias.trim() && mcpName.trim() && recipientEmail.includes("@") && !submitting;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      setResult(await grantMcpAccess({
        keyAlias: keyAlias.trim(),
        mcpName: mcpName.trim(),
        environment,
        recipientEmail: recipientEmail.trim(),
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "MCP erişimi verilemedi");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto grid max-w-xl gap-6">
      <div className="flex items-center gap-2">
        <Plug className="size-5" />
        <h1 className="text-lg font-semibold">MCP erişim</h1>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Mevcut anahtara sunucu ekle</CardTitle>
          <CardDescription>
            Yeni anahtar üretilmez. Alias BRYSL, BRYSEL veya BIREYSEL içermelidir.
            Başarılı işlemden sonra alıcıya bilgi maili gider.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4" onSubmit={onSubmit}>
            <div className="grid gap-1.5">
              <Label htmlFor="grant-alias">Key alias</Label>
              <Input
                id="grant-alias"
                value={keyAlias}
                placeholder="ALZ-BRYSL-EXISTING-KEY"
                onChange={(e) => setKeyAlias(e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="grant-mcp">MCP sunucu adı</Label>
              <Input
                id="grant-mcp"
                value={mcpName}
                placeholder="server adı veya alias"
                onChange={(e) => setMcpName(e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="grant-env">Ortam</Label>
              <select
                id="grant-env"
                value={environment}
                disabled={submitting}
                onChange={(e) => setEnvironment(e.target.value as (typeof ENVIRONMENTS)[number])}
                className={cn(
                  "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm",
                  "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                  "disabled:cursor-not-allowed disabled:opacity-50",
                )}
              >
                {ENVIRONMENTS.map((env) => (
                  <option key={env} value={env}>{env}</option>
                ))}
              </select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="grant-email">Alıcı e-posta</Label>
              <Input
                id="grant-email"
                type="email"
                value={recipientEmail}
                onChange={(e) => setRecipientEmail(e.target.value)}
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={!canSubmit}>
              {submitting && <Loader2 className="size-4 animate-spin" />}
              Erişim ver
            </Button>
          </form>
        </CardContent>
      </Card>
      {result && (
        <Card>
          <CardHeader>
            <CardTitle>{STATUS_LABEL[result.status]}</CardTitle>
            <CardDescription>
              {result.key_alias} · {result.mcp_name} · {result.environment}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-1 text-sm">
            <p>Sunucu id: {result.mcp_server_id}</p>
            <p>{MAIL_LABEL[result.notification.status] ?? result.notification.status}</p>
            <p className="text-muted-foreground">{result.notification.recipient_email}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function GrantMcpPage() {
  return (
    <AdminGuard>
      <GrantContent />
    </AdminGuard>
  );
}
