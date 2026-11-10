"use client";

import { useState, type FormEvent } from "react";
import { KeyRound, Loader2 } from "lucide-react";

import {
  createManualKey,
  fetchLiteLLMTeams,
  type ManualKeyResult,
} from "@/lib/adminApi";
import { AdminGuard } from "@/components/AdminGuard";
import { useAuth } from "@/components/AuthProvider";
import { TeamPicker } from "@/components/TeamPicker";
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

const ENVIRONMENTS = ["DEV", "STG", "PROD", "BIREYSEL"] as const;

function EnvironmentSelect({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <select
      id="key-env"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm",
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

function KeysContent() {
  const { user } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [environment, setEnvironment] = useState("DEV");
  const [modelName, setModelName] = useState("");
  const [teamId, setTeamId] = useState("");
  const [keyAlias, setKeyAlias] = useState("");
  const [maxParallel, setMaxParallel] = useState("");
  const [sendMail, setSendMail] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ManualKeyResult | null>(null);

  if (!user?.is_superuser) {
    return <p className="text-sm text-muted-foreground">Bu sayfa yalnız superuser içindir.</p>;
  }

  const canSubmit =
    name.trim() && email.includes("@") && modelName.trim() && teamId && !submitting;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const teams = await fetchLiteLLMTeams(environment);
      const picked = teams.find((team) => team.team_id === teamId);
      const parallel = maxParallel.trim() ? Number(maxParallel) : null;
      if (parallel !== null && (!Number.isFinite(parallel) || parallel < 1)) {
        throw new Error("Paralel limit en az 1 olmalı");
      }
      const created = await createManualKey({
        name: name.trim(),
        email: email.trim(),
        environment,
        modelName: modelName.trim(),
        team: picked?.team_alias || teamId,
        keyAlias: keyAlias.trim(),
        maxParallelRequests: parallel,
        sendMail,
      });
      setResult(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Key oluşturulamadı");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto grid max-w-xl gap-6">
      <div className="flex items-center gap-2">
        <KeyRound className="size-5" />
        <h1 className="text-lg font-semibold">Key oluştur</h1>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>LiteLLM anahtarı</CardTitle>
          <CardDescription>
            Orion talebi açılmaz. Anahtar yalnızca bu ekranda bir kez gösterilir.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4" onSubmit={onSubmit}>
            <div className="grid gap-1.5">
              <Label htmlFor="key-name">Ad soyad</Label>
              <Input id="key-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="key-email">E-posta</Label>
              <Input
                id="key-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="key-env">Ortam</Label>
              <EnvironmentSelect
                value={environment}
                onChange={(value) => {
                  setEnvironment(value);
                  setTeamId("");
                }}
                disabled={submitting}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="key-model">Model</Label>
              <Input
                id="key-model"
                value={modelName}
                placeholder="allianz-text"
                onChange={(e) => setModelName(e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label>Takım</Label>
              <TeamPicker
                environment={environment}
                value={teamId}
                onChange={setTeamId}
                disabled={submitting}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="key-alias">Alias</Label>
              <Input
                id="key-alias"
                value={keyAlias}
                placeholder="Boşsa takım, ortam ve modelden üretilir"
                onChange={(e) => setKeyAlias(e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="key-parallel">Paralel istek</Label>
              <Input
                id="key-parallel"
                inputMode="numeric"
                value={maxParallel}
                placeholder="Boşsa limit yok"
                onChange={(e) => setMaxParallel(e.target.value)}
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={sendMail}
                onCheckedChange={(checked) => setSendMail(checked === true)}
              />
              Anahtarı e-posta ile gönder
            </label>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={!canSubmit}>
              {submitting && <Loader2 className="size-4 animate-spin" />}
              Key oluştur
            </Button>
          </form>
        </CardContent>
      </Card>
      {result && (
        <Card>
          <CardHeader>
            <CardTitle>Anahtar hazır</CardTitle>
            <CardDescription>
              {result.key_alias}
              {result.mailed ? " — mail gönderildi" : ""}
              {result.mail_error ? ` — ${result.mail_error}` : ""}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2">
            <code className="break-all rounded-md bg-muted p-3 font-mono text-sm">
              {result.api_key}
            </code>
            <Button
              type="button"
              variant="outline"
              onClick={() => navigator.clipboard?.writeText(result.api_key).catch(() => undefined)}
            >
              Kopyala
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function ManualKeyPage() {
  return (
    <AdminGuard>
      <KeysContent />
    </AdminGuard>
  );
}
