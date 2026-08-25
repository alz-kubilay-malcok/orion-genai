import {
  actionResultSchema,
  apiErrorSchema,
  approvalViewSchema,
  type ActionResult,
  type ApprovalViewModel,
} from "./actionSchema";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export type FetchApprovalResult =
  | { ok: true; data: ApprovalViewModel }
  | { ok: false; status: number; errorCode: string };

/**
 * Fetches the read-only approval view for a token from the backend.
 * No mutation is performed; this is safe to call from a server component.
 */
export async function fetchApprovalView(
  token: string,
): Promise<FetchApprovalResult> {
  let res: Response;
  try {
    res = await fetch(
      `${API_BASE_URL}/actions/${encodeURIComponent(token)}/view`,
      { cache: "no-store" },
    );
  } catch {
    return { ok: false, status: 0, errorCode: "UNKNOWN_ERROR" };
  }

  if (!res.ok) {
    let errorCode = "UNKNOWN_ERROR";
    try {
      const body = await res.json();
      errorCode = apiErrorSchema.parse(body).error_code;
    } catch {
      // response body wasn't the expected error shape; keep default code.
    }
    return { ok: false, status: res.status, errorCode };
  }

  const body = await res.json();
  const parsed = approvalViewSchema.parse(body);
  return { ok: true, data: parsed };
}

export type PostActionResult =
  | { ok: true; data: ActionResult }
  | { ok: false; status: number; errorCode: string };

export type ApproveBody = {
  token: string;
  request_version: number;
  allows_all_tools?: boolean | null;
};

export type ReviseBody = {
  token: string;
  request_version: number;
  tpm_approved: number;
  rpm_approved: number;
  admin_note?: string;
  /** Client-facing: booklisteler. None=field'a dokunulmaz; boş array=bilinçli sıfırlama. */
  models?: string[] | null;
  /** Client-facing: yanıt süresi (örn. "24h"). None=field'a dokunulmaz. */
  response_window?: string | null;
  /** Client-facing: kullanım sıklığı (örn. "günlük"). None=field'a dokunulmaz. */
  usage_frequency?: string | null;
};

export type RejectBody = {
  token: string;
  request_version: number;
  reject_reason: string;
};

async function postAction(
  path: "approve" | "revise" | "reject",
  body: ApproveBody | ReviseBody | RejectBody,
): Promise<PostActionResult> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/actions/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    return { ok: false, status: 0, errorCode: "UNKNOWN_ERROR" };
  }

  const json = await res.json().catch(() => null);

  if (!res.ok) {
    let errorCode = "UNKNOWN_ERROR";
    try {
      errorCode = apiErrorSchema.parse(json).error_code;
    } catch {
      // response body wasn't the expected error shape; keep default code.
    }
    return { ok: false, status: res.status, errorCode };
  }

  return { ok: true, data: actionResultSchema.parse(json) };
}

export const postApprove = (body: ApproveBody) => postAction("approve", body);
export const postRevise = (body: ReviseBody) => postAction("revise", body);
export const postReject = (body: RejectBody) => postAction("reject", body);

