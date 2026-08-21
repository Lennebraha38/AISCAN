"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, clearTokens } from "../../lib/api";

interface AnalysisRow {
  id: string;
  study_id: string;
  status: string;
  fusion_risk_score: number;
  created_at: string;
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
        </div>

        <div className="card">
          <h3>Son Analizler</h3>
          <table className="list">
            <thead>
              <tr>
                <th>Tarih</th>
                <th>Risk Skoru</th>
                <th>Durum</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {analyses.map((a) => (
                <tr key={a.id}>
                  <td>{new Date(a.created_at).toLocaleString("tr-TR")}</td>
                  <td>{a.fusion_risk_score.toFixed(1)}</td>
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
                  <td colSpan={4} style={{ color: "#8a93ab" }}>
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
