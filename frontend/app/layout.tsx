import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pulsar-KKDS",
  description: "KVKK uyumlu multimodal tıbbi karar destek platformu (SaMD)",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr">
      <body>
        {/* MDR / SaMD zorunlu uyarı bandı — tüm sayfalarda görünür */}
        <div className="samd-band">
          Bu sistem bir <strong>Karar Destek Sistemidir (SaMD)</strong>. Nihai klinik karar hekim
          sorumluluğundadır.
        </div>
        {children}
      </body>
    </html>
  );
}
