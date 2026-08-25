"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Plus, Trash2, KeyRound } from "lucide-react";

import {
  createLdapMapping,
  deleteLdapMapping,
  listLdapMappings,
  type LdapMappingItem,
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

function CreateForm({
  onCreated,
}: {
  onCreated: () => void;
}) {
  const [orgId, setOrgId] = useState("");
  const [groupDn, setGroupDn] = useState("");
  const [role, setRole] = useState("");
  const [namespaceId, setNamespaceId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmedGroupDn = groupDn.trim();
  const trimmedOrg = orgId.trim();
  const trimmedRole = role.trim();
  const trimmedNs = namespaceId.trim();
  const canSubmit =
    trimmedOrg.length > 0 &&
    trimmedGroupDn.length >= 3 &&
    trimmedRole.length > 0 &&
    !submitting;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await createLdapMapping({
        org_id: trimmedOrg,
        group_dn: trimmedGroupDn,
        role: trimmedRole,
        namespace_id: trimmedNs === "" ? undefined : trimmedNs,
      });
      setOrgId("");
      setGroupDn("");
      setRole("");
      setNamespaceId("");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mapping oluşturulamadı");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Plus className="size-4" /> Yeni LDAP mapping
        </CardTitle>
        <CardDescription>
          AD'deki bir grup DN'si bir panel rolüne bağlanır; ilk eşleşen
          kural oturum açan kullanıcıya uygulanır.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="grid grid-cols-1 gap-4 sm:grid-cols-2" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ldap-org">Organization ID</Label>
            <Input
              id="ldap-org"
              value={orgId}
              onChange={(e) => setOrgId(e.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              required
              disabled={submitting}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ldap-group">LDAP Group DN</Label>
            <Input
              id="ldap-group"
              value={groupDn}
              onChange={(e) => setGroupDn(e.target.value)}
              placeholder="CN=genai-admin,OU=Groups,DC=allianz-tr,DC=local"
              required
              minLength={3}
              disabled={submitting}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ldap-role">Rol</Label>
            <Input
              id="ldap-role"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="admin | editor | viewer | redteam_operator"
              required
              disabled={submitting}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="ldap-ns">Namespace ID (opsiyonel)</Label>
            <Input
              id="ldap-ns"
              value={namespaceId}
              onChange={(e) => setNamespaceId(e.target.value)}
              placeholder="boş bırakılabilir"
              disabled={submitting}
            />
          </div>
          <div className="flex flex-col gap-1 sm:col-span-2">
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="self-start" disabled={!canSubmit}>
              {submitting && <Loader2 className="size-4 animate-spin" />}
              Ekle
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function MappingsTable({
  items,
  onDelete,
}: {
  items: LdapMappingItem[];
  onDelete: (id: string) => void;
}) {
  if (items.length === 0) {
    return (
      <Card>
        <CardContent className="py-6 text-sm text-muted-foreground">
          Henüz mapping tanımlı değil. Yukarıdaki formdan ilk kuralı ekleyin.
        </CardContent>
      </Card>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      {items.map((m) => (
        <Card key={m.id}>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div className="flex flex-col gap-1 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">{m.role}</Badge>
                <span className="font-mono text-xs text-muted-foreground">{m.org_id}</span>
              </div>
              <code className="font-mono text-xs break-all">{m.group_dn}</code>
              {m.namespace_id && (
                <span className="text-xs text-muted-foreground">
                  Namespace: <code className="font-mono">{m.namespace_id}</code>
                </span>
              )}
              <span className="text-xs text-muted-foreground">
                Created: {new Date(m.created_at).toLocaleString("tr-TR")}
              </span>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onDelete(m.id)}
              aria-label="Mapping sil"
            >
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function LdapMappingsContent() {
  const { user } = useAuth();
  const [orgId, setOrgId] = useState<string | null>(null);
  const [items, setItems] = useState<LdapMappingItem[] | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  // superuser için env'den gelen bootstrap admin'i fallback olarak kullanmıyoruz;
  // mevcut kullanıcının org_id'sini bağlamıyoruz, ayrı bir alanla seçtiriyoruz.
  const orgFromUser = useMemo(() => user?.id ?? null, [user]);

  useEffect(() => {
    if (!orgFromUser) return;
    if (orgId === null) setOrgId(orgFromUser);
  }, [orgFromUser, orgId]);

  const refresh = useCallback(async () => {
    if (!orgId) return;
    setFeedback(null);
    try {
      const data = await listLdapMappings(orgId);
      setItems(data);
    } catch (err) {
      setItems([]);
      setFeedback({
        kind: "error",
        message:
          err instanceof Error ? err.message : "Mapping listesi alınamadı",
      });
    }
  }, [orgId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleDelete(id: string) {
    setFeedback(null);
    try {
      await deleteLdapMapping(id);
      await refresh();
      setFeedback({ kind: "info", message: "Mapping silindi" });
    } catch (err) {
      setFeedback({
        kind: "error",
        message: err instanceof Error ? err.message : "Mapping silinemedi",
      });
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <KeyRound className="size-5" /> LDAP Mapping
        </h1>
        <p className="text-sm text-muted-foreground">
          Active Directory grup DN'lerini panel rolleriyle eşleştirin. İlk
          eşleşen kural oturum açıldığında uygulanır.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Organization kapsamı</CardTitle>
          <CardDescription>
            Mapping'leri daraltmak istediğiniz organization ID'yi girin.
            Backend bu kapsamda listeleme yapar; boş bırakılırsa mevcut
            kullanıcının ilk organization'ı kullanılır.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Label htmlFor="ldap-org-filter" className="sr-only">
            Organization ID
          </Label>
          <Input
            id="ldap-org-filter"
            value={orgId ?? ""}
            onChange={(e) => setOrgId(e.target.value || null)}
            placeholder="UUID"
          />
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

      <CreateForm onCreated={refresh} />

      {items === null ? (
        <p className="text-sm text-muted-foreground">
          <Loader2 className="mr-2 inline-block size-4 animate-spin" />
          Yükleniyor...
        </p>
      ) : (
        <MappingsTable items={items} onDelete={handleDelete} />
      )}
    </div>
  );
}

export default function LdapMappingsPage() {
  return (
    <AdminGuard>
      <LdapMappingsContent />
    </AdminGuard>
  );
}
