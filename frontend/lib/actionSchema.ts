import { z } from "zod";

/**
 * Mirrors backend `ApprovalViewModel` (apps/api/src/genai_orion_panel_api/schemas/actions.py).
 * Keep in sync manually — no codegen wired yet.
 */
export const approvalViewSchema = z.object({
  action: z.enum(["approve", "revise", "reject"]),
  request_id: z.string(),
  request_type: z.enum(["litellm_key", "mcp_key", "mcp_server_registry"]),
  status: z.string(),
  request_version: z.number(),
  genai_orion_panel_ticket_id: z.string(),
  genai_orion_panel_ticket_url: z.string(),
  requester_name: z.string(),
  requester_email: z.string(),
  environment: z.string(),
  created_at: z.string(),
  detail: z.record(z.string(), z.unknown()),
});

export type ApprovalViewModel = z.infer<typeof approvalViewSchema>;

export const apiErrorSchema = z.object({
  error_code: z.string(),
});

export type ApiError = z.infer<typeof apiErrorSchema>;

/** Response shape shared by approve/revise/reject POST endpoints. */
export const actionResultSchema = z.object({
  request_id: z.string(),
  status: z.string(),
});

export type ActionResult = z.infer<typeof actionResultSchema>;
