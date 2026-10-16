import type { Metadata } from "next";
import "./globals.css";
import { NotificationProvider } from "../lib/notifications";

export const metadata: Metadata = {
  title: "Pulsar-KKDS",
  description: "SaMD hedefli, KVKK ilkeleri gozetilerek tasarlanmis karar destek prototipi",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr">
      <body>
        <NotificationProvider>
          <div className="samd-band">
            Bu sistem <strong>SaMD hedefli bir Karar Destek Prototipidir</strong>; onaylanmis bir
            tibbi cihaz degildir. Nihai klinik karar hekim sorumlulugundadir.
          </div>
          {children}
        </NotificationProvider>
      </body>
    </html>
  );
}
