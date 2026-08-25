import { ExternalLink } from "lucide-react";

import type { ApprovalViewModel } from "@/lib/actionSchema";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { RequestDetailPanel } from "@/components/RequestDetailPanel";

const ACTION_LABELS: Record<ApprovalViewModel["action"], string> = {
  approve: "Onay",
  revise: "Revize",
  reject: "Red",
};

const REQUEST_TYPE_LABELS: Record<ApprovalViewModel["request_type"], string> = {
  litellm_key: "LiteLLM API Anahtarı",
  mcp_key: "MCP Erişim Anahtarı",
  mcp_server_registry: "MCP Sunucu Kaydı",
};

const ACTION_BADGE_VARIANT: Record<
  ApprovalViewModel["action"],
  "default" | "warning" | "destructive"
> = {
  approve: "default",
  revise: "warning",
  reject: "destructive",
};

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 py-2.5 sm:flex-row sm:items-baseline sm:justify-between">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-sm font-medium">{value}</dd>
    </div>
  );
}

export function ApprovalView({ view }: { view: ApprovalViewModel }) {
  return (
    <Card>
      <CardHeader className="gap-2">
        <div className="flex items-center gap-2">
          <Badge variant={ACTION_BADGE_VARIANT[view.action]}>
            {ACTION_LABELS[view.action]} bekleniyor
          </Badge>
          <Badge variant="outline">{view.status}</Badge>
        </div>
        <CardTitle>
          {REQUEST_TYPE_LABELS[view.request_type]} — {view.genai_orion_panel_ticket_id}
        </CardTitle>
        <CardDescription>
          {view.requester_name} tarafından oluşturuldu ({view.requester_email})
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-1">
        <dl className="divide-y divide-border">
          <DetailRow label="Durum" value={view.status} />
          <DetailRow label="Versiyon" value={view.request_version} />
          <DetailRow
            label="Talep eden"
            value={`${view.requester_name} <${view.requester_email}>`}
          />
          <DetailRow label="Ortam" value={view.environment || "—"} />
          <DetailRow
            label="Ticket"
            value={
              <a
                href={view.genai_orion_panel_ticket_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
              >
                {view.genai_orion_panel_ticket_id}
                <ExternalLink className="size-3.5" />
              </a>
            }
          />
          <DetailRow
            label="Oluşturulma"
            value={new Date(view.created_at).toLocaleString("tr-TR")}
          />
        </dl>

        {Object.keys(view.detail).length > 0 && (
          <>
            <Separator className="my-4" />
            <RequestDetailPanel view={view} />
          </>
        )}
      </CardContent>
    </Card>
  );
}
