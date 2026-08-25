import { ShieldCheck, ArrowRight, KeyRound, Server, Workflow } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import Link from "next/link";

const REQUEST_TYPES = [
  {
    icon: KeyRound,
    title: "LiteLLM API Anahtarı",
    description:
      "Model çağrısı için ihtiyaç duyulan anahtar talepleri; departman, model seti ve eşzamanlı istek limiti ile gelir.",
    type: "litellm_api_anahtari",
  },
  {
    icon: Workflow,
    title: "MCP Erişim Anahtarı",
    description:
      "Bir MCP sunucusuna erişim için talep edilen scope'lu anahtar; araç listesi veya tüm araçlar seçeneği.",
    type: "mcp_erisim_anahtari",
  },
  {
    icon: Server,
    title: "MCP Sunucu Kaydı",
    description:
      "Yeni bir MCP sunucusunun ortama kazandırılması; repo, endpoint ve minimum değerlendirme skoru ile.",
    type: "mcp_sunucu_kaydi",
  },
] as const;

export default function HomePage() {
  return (
    <main className="container flex flex-1 flex-col items-center gap-10 py-16">
      <section className="flex max-w-2xl flex-col items-center gap-4 text-center">
        <div className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
          <ShieldCheck className="size-6" />
        </div>
        <h1 className="text-3xl font-semibold tracking-tight">
          GenAi Orion Requests Panel
        </h1>
        <p className="text-sm text-muted-foreground">
          Onay süreçleri için tek kapı. Talepler webhook üzerinden burada toplanır,
          admin tarafından değerlendirilir ve provision akışına yönlendirilir.
        </p>
        <div className="mt-2 flex gap-2">
          <Button asChild>
            <Link href="/login">
              Yönetim paneline giriş <ArrowRight className="size-4" />
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/admin">Taleplere göz at</Link>
          </Button>
        </div>
      </section>

      <Separator />

      <section className="flex w-full flex-col gap-4">
        <h2 className="text-base font-semibold">Desteklenen talep türleri</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {REQUEST_TYPES.map(({ icon: Icon, title, description, type }) => (
            <Card key={type}>
              <CardHeader className="items-start gap-1.5">
                <div className="flex size-9 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
                  <Icon className="size-4" />
                </div>
                <CardTitle className="text-base">{title}</CardTitle>
                <CardDescription className="font-mono text-xs">{type}</CardDescription>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">{description}</CardContent>
            </Card>
          ))}
        </div>
      </section>

      <Separator />

      <section className="flex max-w-xl flex-col items-center gap-2 text-center text-xs text-muted-foreground">
        <p>
          Bu uygulama onay bağlantılarını görüntülemek için de kullanılır. Bir token'lı
          bağlantı açtığınızda, ilgili karar (
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono">approve</code> /{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono">revise</code> /{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono">reject</code>) karşınıza çıkar.
        </p>
      </section>
    </main>
  );
}
