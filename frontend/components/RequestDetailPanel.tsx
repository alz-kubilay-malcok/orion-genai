import { ExternalLink } from "lucide-react";

import type { ApprovalViewModel } from "@/lib/actionSchema";
import { Badge } from "@/components/ui/badge";

type Detail = ApprovalViewModel["detail"];

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <div className="flex flex-col gap-1 py-2 sm:flex-row sm:items-baseline sm:justify-between">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium sm:text-right">{value}</dd>
    </div>
  );
}

function ChipList({ items }: { items: string[] }) {
  return (
    <div className="flex flex-wrap justify-end gap-1.5">
      {items.map((item) => (
        <Badge key={item} variant="secondary">
          {item}
        </Badge>
      ))}
    </div>
  );
}

function LiteLLMKeyDetails({ detail }: { detail: Detail }) {
  const models = asStringArray(detail.models);
  return (
    <dl className="divide-y divide-border">
      <Field label="Departman" value={asString(detail.department_name)} />
      <Field label="Kullanım amacı" value={asString(detail.purpose_code)} />
      <Field label="Kullanım senaryosu" value={asString(detail.use_case)} />
      {models.length > 0 && <Field label="Modeller" value={<ChipList items={models} />} />}
      <Field label="Yanıt süresi" value={asString(detail.response_window)} />
      <Field label="Kullanım sıklığı" value={asString(detail.usage_frequency)} />
      <Field label="LiteLLM team" value={asString(detail.litellm_team_id) ?? asString(detail.department_name)} />
      <Field label="Anlık paralel istek" value={asNumber(detail.max_concurrent_requests)} />
      <Field label="Anahtar takma adı" value={asString(detail.key_alias)} />
    </dl>
  );
}

function McpKeyDetails({ detail }: { detail: Detail }) {
  const tools = asStringArray(detail.mcp_tool_names);
  const allTools = detail.all_tools === true;
  return (
    <dl className="divide-y divide-border">
      <Field label="Departman" value={asString(detail.department_name)} />
      <Field label="Kullanım amacı" value={asString(detail.purpose_text)} />
      <Field label="MCP sunucusu" value={asString(detail.mcp_server_slug)} />
      <Field
        label="Araçlar"
        value={allTools ? <Badge>Tüm araçlar</Badge> : tools.length > 0 ? <ChipList items={tools} /> : undefined}
      />
      <Field label="Anahtar takma adı" value={asString(detail.key_alias)} />
    </dl>
  );
}

function McpRegistryDetails({ detail }: { detail: Detail }) {
  const repoUrl = asString(detail.repo_url);
  const endpointUrl = asString(detail.endpoint_url);
  return (
    <dl className="divide-y divide-border">
      <Field label="Departman" value={asString(detail.department_name)} />
      <Field label="Sunucu adı" value={asString(detail.mcp_server_display_name)} />
      <Field label="Proje / slug" value={asString(detail.server_slug ?? detail.project_name)} />
      <Field label="Teknik sorumlu" value={asString(detail.technical_owner_email)} />
      <Field label="Kullanım amacı" value={asString(detail.purpose_text)} />
      <Field label="Repo platformu" value={asString(detail.repo_platform)} />
      <Field
        label="Repo"
        value={
          repoUrl && (
            <a
              href={repoUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
            >
              Repo bağlantısı <ExternalLink className="size-3.5" />
            </a>
          )
        }
      />
      <Field label="DevOps Jira" value={asString(detail.devops_jira_key)} />
      <Field
        label="Endpoint"
        value={
          endpointUrl && (
            <a
              href={endpointUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
            >
              {endpointUrl} <ExternalLink className="size-3.5" />
            </a>
          )
        }
      />
      <Field label="Min. değerlendirme skoru" value={asNumber(detail.minimum_evaluation_score)} />
      <Field label="Notlar" value={asString(detail.additional_notes)} />
      <Field
        label="Tüm araçlara izin"
        value={
          detail.registry_allows_all_tools !== undefined ? (
            <Badge variant={detail.registry_allows_all_tools ? "default" : "outline"}>
              {detail.registry_allows_all_tools ? "Evet" : "Hayır"}
            </Badge>
          ) : undefined
        }
      />
    </dl>
  );
}

const PANELS: Record<
  ApprovalViewModel["request_type"],
  (props: { detail: Detail }) => React.ReactElement
> = {
  litellm_key: LiteLLMKeyDetails,
  mcp_key: McpKeyDetails,
  mcp_server_registry: McpRegistryDetails,
};

export function RequestDetailPanel({
  view,
}: {
  view: Pick<ApprovalViewModel, "request_type" | "detail">;
}) {
  const Panel = PANELS[view.request_type];
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-semibold">Talep detayları</h2>
      <Panel detail={view.detail} />
    </section>
  );
}
