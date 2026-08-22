"use client";

import { useEffect } from "react";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Rebuild sonrası tarayıcıda kalan eski chunk referansları için tek seferlik otomatik yenileme.
    if (/chunk|Loading|dynamically imported/i.test(error?.message ?? "")) {
      const key = "pulsar_chunk_reload";
      if (!sessionStorage.getItem(key)) {
        sessionStorage.setItem(key, "1");
        window.location.reload();
      }
    }
  }, [error]);

  return (
    <main className="container" style={{ maxWidth: 480, marginTop: 80 }}>
      <div className="card" style={{ textAlign: "center" }}>
        <h1 style={{ marginTop: 0 }}>Bir hata oluştu</h1>
        <p style={{ color: "#66708a", fontSize: 14 }}>
          Sayfa beklenmedik bir şekilde durdu. Tekrar denemek için aşağıdaki düğmeyi kullanın.
        </p>
        <button className="btn" onClick={() => reset()}>
          Tekrar Dene
        </button>
      </div>
    </main>
  );
}
