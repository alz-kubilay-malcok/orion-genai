import type { Metadata } from "next";
import "./globals.css";

import { AuthProvider } from "@/components/AuthProvider";

export const metadata: Metadata = {
  title: "GenAi Orion Requests Panel",
  description: "GenAi Orion Requests Panel approval viewer",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="tr">
      <body className="min-h-screen bg-background text-foreground antialiased">
        <AuthProvider>
          <div className="flex min-h-screen flex-col">
            <header className="border-b bg-card">
              <div className="container flex h-14 items-center">
                <span className="text-sm font-semibold tracking-tight">
                  GenAi Orion Requests Panel
                </span>
              </div>
            </header>
            <div className="flex flex-1 flex-col">{children}</div>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
