"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Users } from "lucide-react";

import {
  listAdminUsers,
  patchAdminUser,
  type AdminUserItem,
} from "@/lib/adminApi";
import { AdminGuard } from "@/components/AdminGuard";
import { useAuth } from "@/components/AuthProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type Feedback =
  | { kind: "info"; message: string }
  | { kind: "error"; message: string };

function UsersContent() {
  const { user } = useAuth();
  const [items, setItems] = useState<AdminUserItem[] | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const rows = await listAdminUsers();
    setItems(rows);
  }, []);

  useEffect(() => {
    let cancelled = false;
    listAdminUsers()
      .then((rows) => {
        if (!cancelled) setItems(rows);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setItems([]);
          setFeedback({
            kind: "error",
            message: err instanceof Error ? err.message : "Liste alınamadı",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handlePatch(
    row: AdminUserItem,
    body: { is_superuser?: boolean; is_active?: boolean },
  ) {
    setBusyId(row.id);
    setFeedback(null);
    try {
      await patchAdminUser(row.id, body);
      await refresh();
    } catch (err) {
      setFeedback({
        kind: "error",
        message: err instanceof Error ? err.message : "Güncellenemedi",
      });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Users className="size-5" /> Kullanıcı Yönetimi
        </h1>
        <p className="text-sm text-muted-foreground">
          LDAP_ADMIN_GROUP üyeleri ve bootstrap admin aynı yetkiye sahip.
          Panelden verilen superuser, sonraki LDAP login’de silinmez.
        </p>
      </div>

      {feedback && (
        <p
          className={
            feedback.kind === "error"
              ? "text-sm text-destructive"
              : "text-sm text-muted-foreground"
          }
        >
          {feedback.message}
        </p>
      )}

      {items === null ? (
        <p className="text-sm text-muted-foreground">
          <Loader2 className="mr-2 inline-block size-4 animate-spin" />
          Yükleniyor...
        </p>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Henüz kullanıcı yok. LDAP ile ilk girişte kayıt oluşur.
          </CardContent>
        </Card>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((row) => {
            const isSelf = user?.id === row.id;
            const busy = busyId === row.id;
            return (
              <li key={row.id}>
                <Card>
                  <CardHeader className="pb-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <CardTitle className="text-base">
                        {row.display_name || row.username}
                        {isSelf ? " (sen)" : ""}
                      </CardTitle>
                      <div className="flex flex-wrap gap-1.5">
                        <Badge variant={row.is_superuser ? "success" : "secondary"}>
                          {row.is_superuser ? "Superuser" : "Kullanıcı"}
                        </Badge>
                        <Badge variant={row.is_active ? "outline" : "warning"}>
                          {row.is_active ? "Aktif" : "Pasif"}
                        </Badge>
                        <Badge variant="outline">
                          {row.is_ldap ? "LDAP" : "Yerel"}
                        </Badge>
                      </div>
                    </div>
                    <CardDescription>
                      {row.username} · {row.email}
                      {row.last_login_at
                        ? ` · son giriş ${new Date(row.last_login_at).toLocaleString("tr-TR")}`
                        : ""}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={busy || isSelf}
                      onClick={() =>
                        void handlePatch(row, { is_superuser: !row.is_superuser })
                      }
                    >
                      {busy && <Loader2 className="size-4 animate-spin" />}
                      {row.is_superuser ? "Superuser al" : "Superuser ver"}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={busy || isSelf}
                      onClick={() =>
                        void handlePatch(row, { is_active: !row.is_active })
                      }
                    >
                      {row.is_active ? "Pasifleştir" : "Aktifleştir"}
                    </Button>
                  </CardContent>
                </Card>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default function UsersPage() {
  return (
    <AdminGuard>
      <UsersContent />
    </AdminGuard>
  );
}
