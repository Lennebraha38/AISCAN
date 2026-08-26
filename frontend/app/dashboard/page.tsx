"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, clearTokens, getTokens } from "../../lib/api";

interface AnalysisRow {
  id: string;
  study_id: string;
  status: string;
  fusion_risk_score: number;
  created_at: string;
  modality?: string | null;
  top_finding?: string | null;
}

function riskColor(v: number): string | undefined {
  return v >= 65 ? "#c0392b" : v >= 35 ? "#b7791f" : undefined;
}

export default function DashboardPage() {
  const [analyses, setAnalyses] = useState<AnalysisRow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .listAnalyses()
      .then(setAnalyses)
      .catch((e) => setError(e.message));
  }, []);

  const pending = analyses.filter((a) => a.status === "PENDING_REVIEW").length;
  const approved = analyses.filter((a) => a.status === "APPROVED").length;
  const highRisk = analyses.filter((a) => a.fusion_risk_score >= 65).length;

  return (
    <>
      <nav className="navbar">
        <span className="brand">Pulsar-KKDS</span>
        <Link href="/dashboard">Panel</Link>
        <Link href="/studies/new">Yeni Çalışma</Link>
        <Link href="/approvals">Onay Bekleyenler ({pending})</Link>
        {getTokens()?.role === "admin" && (
          <Link href="/admin/audit">Denetim Kaydı</Link>
        )}
        <span style={{ flex: 1 }} />
        <a
          href="#"
          onClick={(e) => {
            e.preventDefault();
            clearTokens();
            window.location.href = "/login";
          }}
        >
          Çıkış
        </a>
      </nav>
      <main className="container">
        <h1>Klinik Karar Destek Paneli</h1>
        {error && <p style={{ color: "#c0392b" }}>{error}</p>}

        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          <div className="card" style={{ flex: 1, minWidth: 200 }}>
            <h3>Bekleyen Onay</h3>
            <p style={{ fontSize: 32, margin: 0 }}>{pending}</p>
          </div>
          <div className="card" style={{ flex: 1, minWidth: 200 }}>
            <h3>Onaylanan Analiz</h3>
            <p style={{ fontSize: 32, margin: 0 }}>{approved}</p>
          </div>
          <div className="card" style={{ flex: 1, minWidth: 200 }}>
            <h3>Yüksek Risk (≥65)</h3>
            <p style={{ fontSize: 32, margin: 0, color: highRisk ? "#c0392b" : undefined }}>
              {highRisk}
            </p>
          </div>
          {analyses.length > 0 && (
            <div className="card" style={{ flex: 2, minWidth: 280 }}>
              <h3>Risk Dağılımı</h3>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height: 90 }}>
                {[0, 1, 2, 3, 4].map((b) => {
                  const n = analyses.filter(
                    (a) => a.fusion_risk_score >= b * 20 && a.fusion_risk_score < (b + 1) * 20 ||
                      (b === 4 && a.fusion_risk_score === 100)
                  ).length;
                  const colors = ["#2e9e5b", "#7cb342", "#d9a441", "#e07b39", "#c0392b"];
                  const max = Math.max(1, ...[0, 1, 2, 3, 4].map(
                    (k) => analyses.filter(
                      (a) => a.fusion_risk_score >= k * 20 && a.fusion_risk_score < (k + 1) * 20 ||
                        (k === 4 && a.fusion_risk_score === 100)
                    ).length
                  ));
                  return (
                    <div key={b} style={{ flex: 1, textAlign: "center" }}>
                      <div style={{ fontSize: 12, color: "#66708a" }}>{n}</div>
                      <div
                        title={`${b * 20}–${(b + 1) * 20}: ${n} vaka`}
                        style={{
                          height: `${Math.round((n / max) * 62) + (n ? 6 : 0)}px`,
                          background: colors[b],
                          borderRadius: 4,
                          opacity: n ? 1 : 0.15,
                          marginTop: 2,
                        }}
                      />
                      <small style={{ color: "#8a93ab" }}>{b * 20}–{(b + 1) * 20}</small>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="card">
          <h3>Son Analizler</h3>
          <table className="list">
            <thead>
              <tr>
                <th>Tarih</th>
                <th>Vaka</th>
                <th>Risk Skoru</th>
                <th>Durum</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {analyses.map((a) => (
                <tr key={a.id}>
                  <td>{new Date(a.created_at).toLocaleString("tr-TR")}</td>
                  <td>
                    {a.top_finding
                      ? <strong>{a.top_finding}</strong>
                      : <small style={{ color: "#8a93ab" }}>{a.modality ?? "—"} · bulgu yok</small>}
                  </td>
                  <td style={{ color: riskColor(a.fusion_risk_score), fontWeight: 600 }}>
                    {a.fusion_risk_score.toFixed(1)}
                  </td>
                  <td>
                    <span className={`badge ${a.status.toLowerCase()}`}>
                      {a.status === "PENDING_REVIEW"
                        ? "⏳ Hekim onayı bekliyor"
                        : a.status === "APPROVED"
                          ? "✓ Onaylandı"
                          : "✗ Reddedildi"}
                    </span>
                  </td>
                  <td>
                    <Link href={`/viewer/${a.study_id}`}>Görüntüle</Link>
                  </td>
                </tr>
              ))}
              {!analyses.length && (
                <tr>
                  <td colSpan={5} style={{ color: "#8a93ab" }}>
                    Henüz analiz yok.{" "}
                    <Link href="/studies/new">İlk çalışmayı oluştur</Link>.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </main>
    </>
  );
}
