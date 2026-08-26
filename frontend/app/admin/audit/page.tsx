"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
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

const ACTION_INFO: Record<string, { desc: string; icon: string }> = {
  LOGIN: { desc: "Sisteme giriş yapıldı.", icon: "🔑" },
  LOGIN_FAILED: { desc: "Başarısız giriş denemesi (hatalı e-posta veya şifre).", icon: "⛔" },
  USER_CREATED: { desc: "Admin yeni bir kullanıcı hesabı açtı.", icon: "👤" },
  PASSWORD_CHANGED: { desc: "Kullanıcı kendi şifresini değiştirdi.", icon: "🔒" },
  STUDY_CREATED: { desc: "Yeni çalışma (anonim vaka) oluşturuldu.", icon: "🗂" },
  ANALYSIS_CREATED: { desc: "Yapay zeka analizi üretildi ve hekim onayı bekliyor.", icon: "🧠" },
  REPORT_DOWNLOADED: { desc: "Resmi rapor PDF'i indirildi.", icon: "📄" },
  DECISION_APPROVED: { desc: "Hekim raporu ONAYLADI — rapor kesinleşti.", icon: "✅" },
  DECISION_REJECTED: { desc: "Hekim raporu REDDETTİ.", icon: "❌" },
};

/** Yalnız admin: KVKK/MDR denetim kaydı görüntüleyici. */
export default function AuditPage() {
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [linkedStudy, setLinkedStudy] = useState<Record<string, string>>({});
  const [cases, setCases] = useState<Awaited<ReturnType<typeof api.listAnalyses>>>([]);

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
    api.listAnalyses().then(setCases).catch(() => {});
  }, []);

  const stats = useMemo(() => {
    const n = cases.length || 1;
    const appr = cases.filter((c) => c.status === "APPROVED").length;
    const rej = cases.filter((c) => c.status === "REJECTED").length;
    const pend = cases.filter((c) => c.status === "PENDING_REVIEW").length;
    const avg = cases.reduce((s, c) => s + c.fusion_risk_score, 0) / n;
    const counts = new Map<string, number>();
    for (const c of cases) if (c.top_finding) counts.set(c.top_finding, (counts.get(c.top_finding) ?? 0) + 1);
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
    return { total: cases.length, appr, rej, pend, avg, top };
  }, [cases]);

  // Analiz olaylarında ilgili vakanın viewer linkini çöz.
  async function resolveLink(row: AuditRow) {
    if (row.entity_type !== "analysis" || !row.entity_id) return;
    if (linkedStudy[row.entity_id] !== undefined) {
      setOpenId(openId === row.id ? null : row.id);
      return;
    }
    setOpenId(openId === row.id ? null : row.id);
    try {
      const a = await api.getAnalysis(row.entity_id);
      setLinkedStudy((m) => ({ ...m, [row.entity_id as string]: a.study_id }));
    } catch {
      setLinkedStudy((m) => ({ ...m, [row.entity_id as string]: "" }));
    }
  }

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
        (son 200 kayıt). Detay için bir satıra tıklayın.
      </p>
      {error && <p style={{ color: "#c0392b" }}>{error}</p>}

      {!error && stats.total > 0 && (
        <div className="card" style={{ marginBottom: 14 }}>
          <h3>Karar İstatistikleri</h3>
          <div style={{ display: "flex", gap: 22, flexWrap: "wrap", fontSize: 14 }}>
            <span>Toplam analiz: <strong>{stats.total}</strong></span>
            <span style={{ color: "#1e8e4e" }}>Onaylı: <strong>{stats.appr}</strong> (%{Math.round((stats.appr / stats.total) * 100)})</span>
            <span style={{ color: "#c0392b" }}>Reddedilen: <strong>{stats.rej}</strong></span>
            <span>Bekleyen: <strong>{stats.pend}</strong></span>
            <span>Ortalama risk: <strong>{stats.avg.toFixed(1)}</strong></span>
            {stats.top && <span>En sık bulgu: <strong>{stats.top[0]}</strong> ({stats.top[1]}×)</span>}
          </div>
        </div>
      )}

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
                <th></th>
                <th>Zaman (UTC)</th>
                <th>İşlem</th>
                <th>Nesne</th>
                <th>Kullanıcı</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => {
                const info = ACTION_INFO[r.action] ?? { desc: r.action, icon: "•" };
                const open = openId === r.id;
                const sid = r.entity_id ? linkedStudy[r.entity_id] : undefined;
                return (
                  <Fragment key={r.id}>
                    <tr
                      onClick={() => resolveLink(r)}
                      style={{ cursor: "pointer", background: open ? "#f3f8ff" : undefined }}
                    >
                      <td>{open ? "▾" : "▸"}</td>
                      <td><small>{new Date(r.created_at + "Z").toLocaleString("tr-TR")}</small></td>
                      <td><strong>{info.icon} {r.action}</strong></td>
                      <td><code>{(r.entity_id ?? "-").slice(0, 10)}…</code></td>
                      <td><code>{(r.user_id ?? "-").slice(0, 8)}…</code></td>
                      <td><small>{r.ip ?? "-"}</small></td>
                    </tr>
                    {open && (
                      <tr>
                        <td colSpan={6} style={{ background: "#fbfcff" }}>
                          <div style={{ padding: "8px 14px", fontSize: 14 }}>
                            <p style={{ margin: "4px 0" }}>{info.desc}</p>
                            <table style={{ fontSize: 13, borderSpacing: "4px 2px" }}>
                              <tbody>
                                <tr><td style={{ color: "#66708a", paddingRight: 12 }}>Olay kimliği</td><td><code>{r.id}</code></td></tr>
                                <tr><td style={{ color: "#66708a", paddingRight: 12 }}>Tam zaman</td><td><code>{r.created_at} UTC</code></td></tr>
                                <tr><td style={{ color: "#66708a", paddingRight: 12 }}>Nesne türü / kimliği</td><td><code>{r.entity_type} · {r.entity_id ?? "-"}</code></td></tr>
                                <tr><td style={{ color: "#66708a", paddingRight: 12 }}>Kullanıcı kimliği</td><td><code>{r.user_id ?? "(anonim/başarısız deneme)"}</code></td></tr>
                                <tr><td style={{ color: "#66708a", paddingRight: 12 }}>Kaynak IP</td><td><code>{r.ip ?? "-"}</code></td></tr>
                                <tr><td style={{ color: "#66708a", paddingRight: 12 }}>Kayıt bütünlük hash'i</td><td><code>{r.data_hash ?? "-"}</code></td></tr>
                              </tbody>
                            </table>
                            {r.entity_type === "analysis" && (
                              <p style={{ margin: "8px 0 2px" }}>
                                {sid ? (
                                  <Link href={`/viewer/${sid}`}>→ İlgili vakayı görüntüleyicide aç</Link>
                                ) : (
                                  <small style={{ color: "#8a93ab" }}>Vaka bağlantısı çözülüyor…</small>
                                )}
                              </p>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
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
