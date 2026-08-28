import type { Metadata } from "next";
import "./globals.css";
import { NotificationProvider } from "../lib/notifications";

export const metadata: Metadata = {
  title: "Pulsar-KKDS",
  description: "KVKK uyumlu multimodal tibbi karar destek platformu (SaMD)",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr">
      <body>
        <NotificationProvider>
          <div className="samd-band">
            Bu sistem bir <strong>Karar Destek Sistemidir (SaMD)</strong>. Nihai klinik karar hekim
            sorumlulugundadir.
          </div>
          {children}
        </NotificationProvider>
      </body>
    </html>
  );
}
