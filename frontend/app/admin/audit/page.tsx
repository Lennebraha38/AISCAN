"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, getTokens } from "../../../lib/api";

interface AuditRow {
  id: string;
  user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  data_hash: string | null;
  ip: string | null;
  created_at: string;
}

/** Yalnız admin: KVKK/MDR denetim kaydı görüntüleyici. */
export default function AuditPage() {
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");

  useEffect(() => {
    const t = getTokens();
    if (t?.role !== "admin") {
      setError("Bu sayfa yalnız admin rolüne açıktır.");
      return;
    }
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/v1/audit/logs`, {
      headers: { Authorization: `Bearer ${t.access_token}` },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setRows)
      .catch((e) => setError(e instanceof Error ? e.message : "Kayıtlar yüklenemedi"));
  }, []);

  const shown = (rows ?? []).filter(
    (r) =>
      !filter ||
      r.action.toLowerCase().includes(filter.toLowerCase()) ||
      (r.entity_id ?? "").toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <main className="container">
      <nav className="navbar" style={{ margin: "-24px -16px 16px", borderRadius: 8 }}>
        <Link href="/dashboard">← Panel</Link>
        <span style={{ flex: 1 }} />
        <span className="badge approved">DENETİM KAYDI</span>
      </nav>

      <h1>Denetim Kaydı (Audit Trail)</h1>
      <p style={{ color: "#66708a", fontSize: 14 }}>
        KVKK/MDR uyumu için tüm kritik olaylar değişmez zaman damgasıyla kayıt altındadır
        (son 200 kayıt). Her satır kullanıcı, işlem, nesne ve IP bilgisi taşır.
      </p>
      {error && <p style={{ color: "#c0392b" }}>{error}</p>}

      {!error && (
        <>
          <input
            placeholder="Filtre: işlem veya nesne kimliği…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ maxWidth: 340 }}
          />
          <table className="list" style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Zaman (UTC)</th>
                <th>İşlem</th>
                <th>Nesne</th>
                <th>Kullanıcı</th>
                <th>IP</th>
                <th>Kayıt hash'i</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.id}>
                  <td><small>{new Date(r.created_at + "Z").toLocaleString("tr-TR")}</small></td>
                  <td>
                    <strong>{r.action}</strong>
                    <br />
                    <small>{r.entity_type}</small>
                  </td>
                  <td><code>{(r.entity_id ?? "-").slice(0, 10)}…</code></td>
                  <td><code>{(r.user_id ?? "-").slice(0, 8)}…</code></td>
                  <td><small>{r.ip ?? "-"}</small></td>
                  <td><small style={{ color: "#8a93ab" }}>{(r.data_hash ?? "").slice(0, 10)}</small></td>
                </tr>
              ))}
              {rows && !shown.length && (
                <tr><td colSpan={6} style={{ color: "#8a93ab" }}>Kayıt bulunamadı</td></tr>
              )}
              {!rows && !error && (
                <tr><td colSpan={6}>Yükleniyor…</td></tr>
              )}
            </tbody>
          </table>
        </>
      )}
    </main>
  );
}
