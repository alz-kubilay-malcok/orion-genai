"use client";

import Link from "next/link";
import { KeyRound, Users } from "lucide-react";

import { AdminGuard } from "@/components/AdminGuard";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";

function DeprecationContent() {
  return (
    <div className="flex flex-col gap-6 sm:max-w-2xl">
      <div className="flex flex-col gap-1">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Users className="size-5" /> Kullanıcı Yönetimi (Eski)
        </h1>
        <p className="text-sm text-muted-foreground">
          LDAP/AD entegrasyonu ile birlikte kullanıcı kayıtları artık
          dizin tarafından yönetiliyor. Panelde kullanıcı oluşturma /
          silme işlemleri kaldırıldı.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Yetkilendirme nasıl çalışıyor?</CardTitle>
          <CardDescription>
            Active Directory'deki grup → panel rollerini LDAP mapping
            tablosu üzerinden eşliyoruz.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          <ol className="list-decimal space-y-1 pl-5">
            <li>
              Login sırasında kullanıcı AD'ye bind olur; <code>group_dns</code> çekilir.
            </li>
            <li>
              <code>LDAP mapping</code> tablosundaki ilk eşleşen kurala göre rol atanır.
            </li>
            <li>
              Eşleşme yoksa bootstrap admin (env) veya <code>admin@local</code> break-glass hesabı devreye girer.
            </li>
          </ol>
          <Link href="/admin/ldap-mappings" className="pt-2">
            <Button>
              <KeyRound className="size-4" /> LDAP Mapping ekranına git
            </Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

export default function UsersPage() {
  return (
    <AdminGuard>
      <DeprecationContent />
    </AdminGuard>
  );
}
