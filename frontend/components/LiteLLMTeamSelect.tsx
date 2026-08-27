"use client";

import { cn } from "@/lib/utils";

export type LiteLLMTeamOption = {
  team_id: string;
  team_alias: string;
};

type Props = {
  id?: string;
  teams: LiteLLMTeamOption[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
};

function selectClassName(className?: string) {
  return cn(
    "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors",
    "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
    "disabled:cursor-not-allowed disabled:opacity-50",
    className,
  );
}

export function LiteLLMTeamSelect({ id, teams, value, onChange, disabled }: Props) {
  const options = [...teams];
  if (value && !options.some((t) => t.team_id === value || t.team_alias === value)) {
    options.unshift({ team_id: value, team_alias: value });
  }

  const selected =
    options.find((t) => t.team_id === value)?.team_id
    ?? options.find((t) => t.team_alias === value)?.team_id
    ?? "";

  if (options.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        LiteLLM team listesi alınamadı. Sayfayı yenileyin.
      </p>
    );
  }

  return (
    <select
      id={id}
      className={selectClassName()}
      value={selected}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">Team seçin</option>
      {options.map((team) => (
        <option key={team.team_id} value={team.team_id}>
          {team.team_alias}
        </option>
      ))}
    </select>
  );
}
