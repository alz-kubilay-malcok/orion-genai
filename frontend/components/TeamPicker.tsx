"use client";

import { useEffect, useState } from "react";
import { Loader2, Plus } from "lucide-react";

import { createLiteLLMTeam, fetchLiteLLMTeams, type LiteLLMTeamOptionDto } from "@/lib/adminApi";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LiteLLMTeamSelect } from "@/components/LiteLLMTeamSelect";

type Props = {
  environment: string;
  value: string;
  onChange: (teamId: string) => void;
  disabled?: boolean;
};

/**
 * Gerçek LiteLLM `team_id` seçtiren dropdown + "yeni takım oluştur" mini-form.
 *
 * LiteLLM `/key/generate` ve `/key/update` yalnız var olan `team_id` kabul
 * eder; serbest metin göndermek proxy'de hata aldırır. Bu bileşen kullanıcının
 * her zaman gerçek bir `team_id` seçmesini (veya yeni bir team oluşturup onu
 * seçmesini) zorunlu kılar.
 */
export function TeamPicker({ environment, value, onChange, disabled }: Props) {
  const [teams, setTeams] = useState<LiteLLMTeamOptionDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newAlias, setNewAlias] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchLiteLLMTeams(environment)
      .then((rows) => {
        if (!cancelled) setTeams(rows);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Team listesi alınamadı");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [environment]);

  async function handleCreate() {
    const alias = newAlias.trim();
    if (!alias) return;
    setCreating(true);
    setCreateError(null);
    try {
      const team = await createLiteLLMTeam(environment, alias);
      setTeams((prev) => {
        if (prev.some((t) => t.team_id === team.team_id)) return prev;
        return [...prev, team].sort((a, b) => a.team_alias.localeCompare(b.team_alias));
      });
      onChange(team.team_id);
      setNewAlias("");
      setShowCreate(false);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Team oluşturulamadı");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="grid gap-2">
      <div className="flex items-center gap-2">
        {loading ? (
          <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" /> Team listesi yükleniyor…
          </p>
        ) : (
          <div className="flex-1">
            <LiteLLMTeamSelect teams={teams} value={value} onChange={onChange} disabled={disabled} />
          </div>
        )}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => setShowCreate((v) => !v)}
        >
          <Plus className="size-3.5" /> Yeni takım
        </Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      {showCreate && (
        <div className="flex items-center gap-2 rounded-md border bg-muted/30 p-2">
          <Input
            value={newAlias}
            onChange={(e) => setNewAlias(e.target.value)}
            placeholder="Yeni takım adı (örn. HASAR)"
            className="h-8"
          />
          <Button type="button" size="sm" disabled={!newAlias.trim() || creating} onClick={handleCreate}>
            {creating && <Loader2 className="size-3.5 animate-spin" />}
            Oluştur
          </Button>
        </div>
      )}
      {createError && <p className="text-xs text-destructive">{createError}</p>}
      <p className="text-xs text-muted-foreground">
        LiteLLM yalnız gerçek bir team id kabul eder — serbest metin hata verir.
        Takım yoksa &quot;Yeni takım&quot; ile gerçek bir LiteLLM team oluşturun.
      </p>
    </div>
  );
}
