"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Mail, Plus, Trash2 } from "lucide-react";

import {
  createApprover,
  deleteApprover,
  listApprovers,
  patchApprover,
  type ApproverItem,
} from "@/lib/adminApi";
import { AdminGuard } from "@/components/AdminGuard";
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

function ApproversContent() {
  const [items, setItems] = useState<ApproverItem[] | null>(null);
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  const refresh = useCallback(async () => {
    const rows = await listApprovers();
    setItems(rows);
  }, []);

  useEffect(() => {
    let cancelled = false;
    listApprovers()
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

  const canSubmit = email.trim().includes("@") && !submitting;

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setFeedback(null);
    try {
      await createApprover(email.trim());
      setEmail("");
      await refresh();
      setFeedback({ kind: "info", message: "Onaylayan eklendi" });
    } catch (err) {
      setFeedback({
        kind: "error",
        message: err instanceof Error ? err.message : "Eklenemedi",
      });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleToggle(row: ApproverItem) {
    setFeedback(null);
    try {
      await patchApprover(row.id, { is_active: !row.is_active });
      await refresh();
    } catch (err) {
      setFeedback({
        kind: "error",
        message: err instanceof Error ? err.message : "Güncellenemedi",
      });
    }
  }

  async function handleDelete(row: ApproverItem) {
    if (!window.confirm(`${row.email} listeden silinsin mi?`)) return;
    setFeedback(null);
    try {
      await deleteApprover(row.id);
      await refresh();
      setFeedback({ kind: "info", message: "Kayıt silindi" });
    } catch (err) {
      setFeedback({
        kind: "error",
        message: err instanceof Error ? err.message : "Silinemedi",
      });
    }
  }

  return (
    <div className="flex flex-col gap-6 sm:max-w-2xl">
      <div className="flex flex-col gap-1">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Mail className="size-5" /> Onaylayanlar
        </h1>
        <p className="text-sm text-muted-foreground">
          Yeni talep geldiğinde onay maili bu listedeki aktif adreslere gider.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Plus className="size-4" /> Onaylayan ekle
          </CardTitle>
          <CardDescription>
            E-posta benzersizdir. Pasif bir kayıt yeniden eklenirse tekrar aktif olur.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={handleAdd}>
            <div className="flex min-w-0 flex-1 flex-col gap-1.5">
              <Label htmlFor="approver-email">E-posta</Label>
              <Input
                id="approver-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="onaylayan@allianz.com.tr"
                autoComplete="off"
                required
                disabled={submitting}
              />
            </div>
            <Button type="submit" disabled={!canSubmit}>
              {submitting && <Loader2 className="size-4 animate-spin" />}
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
            Henüz onaylayan yok. Yukarıdan e-posta ekleyin; aksi halde yeni talepler
            onay maili göndermez.
          </CardContent>
        </Card>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((row) => (
            <li key={row.id}>
              <Card>
                <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
                  <div className="flex min-w-0 flex-col gap-1">
                    <span className="truncate font-medium">{row.email}</span>
                    <span className="text-xs text-muted-foreground">
                      {row.created_at
                        ? new Date(row.created_at).toLocaleString("tr-TR")
                        : ""}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={row.is_active ? "success" : "secondary"}>
                      {row.is_active ? "Aktif" : "Pasif"}
                    </Badge>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => void handleToggle(row)}
                    >
                      {row.is_active ? "Pasifleştir" : "Aktifleştir"}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => void handleDelete(row)}
                      aria-label={`${row.email} sil`}
                    >
                      <Trash2 className="size-4 text-destructive" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function ApproversPage() {
  return (
    <AdminGuard>
      <ApproversContent />
    </AdminGuard>
  );
}
