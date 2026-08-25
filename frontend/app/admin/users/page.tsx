"use client";

import { Users } from "lucide-react";

import { AdminGuard } from "@/components/AdminGuard";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

function DeprecationContent() {
  return (
    <div className="flex flex-col gap-6 sm:max-w-2xl">
      <div className="flex flex-col gap-1">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Users className="size-5" /> Kullanıcı Yönetimi
        </h1>
        <p className="text-sm text-muted-foreground">
          Kullanıcılar LDAP/AD veya yerel bootstrap admin ile giriş yapar.
          Panelde kullanıcı oluşturma / silme yoktur.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Yetkilendirme nasıl çalışıyor?</CardTitle>
          <CardDescription>
            LDAP grubu ``LDAP_ADMIN_GROUP`` içinde olan kullanıcılar
            superuser olur; diğer LDAP kullanıcıları giriş yapabilir ama
            admin paneline 403 alır. Mapping UI v1 kapsamı dışındadır.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          <ol className="list-decimal space-y-1 pl-5">
            <li>
              Login sırasında kullanıcı dizine bind olur; parola saklanmaz.
            </li>
            <li>
              ``LDAP_ADMIN_GROUP`` üyeliği ``is_superuser`` olarak yazılır.
            </li>
            <li>
              LDAP kapalıysa veya dizin düşerse bootstrap admin
              (``BOOTSTRAP_ADMIN_*``) yerel bcrypt hesabı ile girer.
            </li>
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}

export default function UsersPage() {
  return (
    <AdminGuard>
      <div className="container py-8">
        <DeprecationContent />
      </div>
    </AdminGuard>
  );
}