import { AlertTriangle, Info } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

type ResultBannerProps = {
  title: string;
  message: string;
  tone?: "error" | "info";
};

export function ResultBanner({ title, message, tone = "info" }: ResultBannerProps) {
  return (
    <Alert variant={tone === "error" ? "destructive" : "default"}>
      {tone === "error" ? <AlertTriangle /> : <Info />}
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}
