import { fetchApprovalView } from "@/lib/api";
import { ApprovalView } from "@/components/ApprovalView";
import { ApprovalActions } from "@/components/ApprovalActions";
import { ResultBanner } from "@/components/ResultBanner";

const ERROR_MESSAGES: Record<string, string> = {
  INVALID_ACTION_TOKEN: "Bağlantının süresi dolmuş veya geçersiz.",
  NOT_FOUND: "Talep bulunamadı.",
  UNKNOWN_ERROR: "Beklenmeyen bir hata oluştu.",
};

const TERMINAL_STATUSES = new Set(["completed", "rejected", "failed", "expired"]);

export default async function ApprovalPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const result = await fetchApprovalView(token);

  return (
    <main className="container flex w-full flex-1 flex-col gap-6 py-10">
      {result.ok ? (
        <>
          <ApprovalView view={result.data} />
          {TERMINAL_STATUSES.has(result.data.status) ? (
            <ResultBanner
              tone="info"
              title="Bu talep zaten sonuçlandırılmış"
              message={`Mevcut durum: ${result.data.status}`}
            />
          ) : (
            <ApprovalActions token={token} view={result.data} />
          )}
        </>
      ) : (
        <ResultBanner
          tone="error"
          title="Görüntülenemedi"
          message={
            ERROR_MESSAGES[result.errorCode] ?? ERROR_MESSAGES.UNKNOWN_ERROR
          }
        />
      )}
    </main>
  );
}
