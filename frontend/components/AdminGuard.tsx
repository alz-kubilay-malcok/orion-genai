"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { LogOut, LayoutDashboard, Users, Mail, FileSpreadsheet, KeyRound } from "lucide-react";

import { useAuth } from "@/components/AuthProvider";
import { Button } from "@/components/ui/button";

export function AdminGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user, loading, logout } = useAuth();

  useEffect(() => {
    if (!loading && user === null) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading) {
    return (
      <div className="container py-10 text-sm text-muted-foreground">
        Yükleniyor...
      </div>
    );
  }

  if (!user) {
    // redirect tetiklenene kadar boş frame; içerik sızdırmıyoruz.
    return null;
  }

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  return (
    <div className="flex flex-1 flex-col">
      <nav className="border-b bg-card">
        <div className="container flex h-12 items-center justify-between">
          <div className="flex items-center gap-4 text-sm">
            <Link href="/admin" className="flex items-center gap-1.5 font-medium">
              <LayoutDashboard className="size-4" /> Bekleyen Talepler
            </Link>
            {user!.is_superuser && (
              <>
                <Link
                  href="/admin/approvers"
                  className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground"
                >
                  <Mail className="size-4" /> Onaylayanlar
                </Link>
                <Link
                  href="/admin/users"
                  className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground"
                >
                  <Users className="size-4" /> Kullanıcılar
                </Link>
                <Link
                  href="/admin/batch-keys"
                  className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground"
                >
                  <FileSpreadsheet className="size-4" /> Toplu key
                </Link>
                <Link
                  href="/admin/keys"
                  className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground"
                >
                  <KeyRound className="size-4" /> Key oluştur
                </Link>
              </>
            )}
          </div>
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <span>
              {user!.username}
              {user!.is_superuser ? " (superuser)" : ""}
            </span>
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="size-4" /> Çıkış
            </Button>
          </div>
        </div>
      </nav>
      <div className="container flex-1 py-8">{children}</div>
    </div>
  );
}
