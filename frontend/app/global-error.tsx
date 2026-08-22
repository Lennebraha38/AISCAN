"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const stale =
    typeof navigator !== "undefined" &&
    /chunk|Loading|dynamically imported/i.test(error?.message ?? "");
  return (
    <html lang="tr">
      <body style={{ fontFamily: "system-ui, sans-serif", background: "#f5f7fb", display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", margin: 0 }}>
        <div style={{ background: "#fff", borderRadius: 12, padding: 32, maxWidth: 440, boxShadow: "0 8px 24px rgba(15,23,42,.08)", textAlign: "center" }}>
          <h1 style={{ fontSize: 20, marginTop: 0 }}>Bir şeyler ters gitti</h1>
          <p style={{ color: "#66708a", fontSize: 14 }}>
            {stale
              ? "Uygulama güncellendi; sayfanın taze bir kopyası yükleniyor."
              : "Beklenmeyen bir hata oluştu. Lütfen tekrar deneyin."}
          </p>
          <button
            onClick={() => {
              if (stale) {
                window.location.reload();
              } else {
                reset();
              }
            }}
            style={{ background: "#2563eb", color: "#fff", border: "none", borderRadius: 8, padding: "10px 20px", fontSize: 14, cursor: "pointer" }}
          >
            Sayfayı Yenile
          </button>
        </div>
      </body>
    </html>
  );
}
