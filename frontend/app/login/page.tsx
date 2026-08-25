"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { LogIn, Loader2 } from "lucide-react";

import { useAuth } from "@/components/AuthProvider";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();

  const canSubmit =
    username.trim().length > 0 && password.length > 0 && !loading;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    const result = await login(username.trim(), password);
    setLoading(false);
    switch (result.kind) {
      case "ok":
        router.push("/admin");
        return;
      case "rate_limit": {
        const retry = Math.max(1, Math.round(result.retryAfter ?? 1));
        setError(`Çok fazla deneme. ${retry} saniye sonra tekrar deneyin.`);
        return;
      }
      case "invalid":
        setError("Kullanıcı adı veya şifre hatalı");
        return;
      case "network":
        setError("Sunucuya ulaşılamadı. Ağınızı kontrol edip tekrar deneyin.");
        return;
    }
  }

  return (
    <main className="container flex flex-1 items-center justify-center py-16">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <LogIn className="size-5" /> Admin Girişi
          </CardTitle>
          <CardDescription>
            Active Directory hesabınızla giriş yapın.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="username">Kullanıcı adı</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                placeholder="kullanici@allianz-tr.local"
                required
                disabled={loading}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">Şifre</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                disabled={loading}
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={!canSubmit}>
              {loading && <Loader2 className="size-4 animate-spin" />}
              Giriş yap
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
