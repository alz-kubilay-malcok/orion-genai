import { fetchApprovalView } from "@/lib/api";
import { ApprovalView } from "@/components/ApprovalView";
import { ApprovalActions } from "@/components/ApprovalActions";
import { ResultBanner } from "@/components/ResultBanner";
import { isSettledStatus } from "@/lib/requestStatus";

const ERROR_MESSAGES: Record<string, string> = {
  INVALID_ACTION_TOKEN: "Bağlantının süresi dolmuş veya geçersiz.",
  NOT_FOUND: "Talep bulunamadı.",
  UNKNOWN_ERROR: "Beklenmeyen bir hata oluştu.",
};

function settledCopy(status: string): { title: string; message: string } {
  if (status === "rejected") {
    return { title: "Bu talep reddedildi", message: "Talep edene red gerekçesi iletildi." };
  }
  if (status === "failed") {
    return { title: "Bu talep başarısız", message: "Sağlama tamamlanamadı." };
  }
  if (status === "completed") {
    return { title: "Bu talep tamamlandı", message: "Anahtar talep edene iletildi." };
  }
  return {
    title: "Talep onaylandı",
    message: "İşlem alındı. Anahtar hazır olunca talep edene mail gider.",
  };
}

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
          {isSettledStatus(result.data.status) ? (
            <ResultBanner
              tone={result.data.status === "rejected" || result.data.status === "failed" ? "error" : "info"}
              {...settledCopy(result.data.status)}
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
