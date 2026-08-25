"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Plus, Users } from "lucide-react";

import {
  createApprover,
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Feedback =
  | { kind: "info"; message: string }
  | { kind: "error"; message: string };

function UsersContent() {
  const { user } = useAuth();
  const [items, setItems] = useState<AdminUserItem[] | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [approverEmail, setApproverEmail] = useState("");
  const [adding, setAdding] = useState(false);

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
    body: { is_superuser?: boolean; is_active?: boolean; is_approver?: boolean },
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

  async function handleAddApprover(e: React.FormEvent) {
    e.preventDefault();
    const value = approverEmail.trim();
    if (!value.includes("@") || adding) return;
    setAdding(true);
    setFeedback(null);
    try {
      await createApprover(value);
      setApproverEmail("");
      await refresh();
      setFeedback({ kind: "info", message: `${value} onaylayan listesine eklendi` });
    } catch (err) {
      setFeedback({
        kind: "error",
        message: err instanceof Error ? err.message : "Onaylayan eklenemedi",
      });
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Users className="size-5" /> Kullanıcı Yönetimi
        </h1>
        <p className="text-sm text-muted-foreground">
          Superuser yetkisi ve onay maili alıcıları buradan yönetilir.
          Henüz giriş yapmamış birini onaylayan yapmak için e-posta eklemen yeterli.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Plus className="size-4" /> Onaylayan ekle
          </CardTitle>
          <CardDescription>
            Onay maili bu adrese gider. Kişinin panele giriş yapmış olması gerekmez.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-3 sm:flex-row sm:items-end"
            onSubmit={(e) => void handleAddApprover(e)}
          >
            <div className="flex min-w-0 flex-1 flex-col gap-1.5">
              <Label htmlFor="approver-email">E-posta</Label>
              <Input
                id="approver-email"
                type="email"
                value={approverEmail}
                onChange={(e) => setApproverEmail(e.target.value)}
                placeholder="onaylayan@allianz.com.tr"
                autoComplete="off"
                required
                disabled={adding}
              />
            </div>
            <Button
              type="submit"
              disabled={adding || !approverEmail.trim().includes("@")}
            >
              {adding && <Loader2 className="size-4 animate-spin" />}
              Ekle
            </Button>
          </form>
        </CardContent>
      </Card>

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
                        <Badge variant={row.is_approver ? "success" : "outline"}>
                          {row.is_approver ? "Onaylayan" : "Onaylayan değil"}
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
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() =>
                        void handlePatch(row, { is_approver: !row.is_approver })
                      }
                    >
                      {row.is_approver ? "Onaylayanlıktan çıkar" : "Onaylayan yap"}
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
