"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "../../lib/api";

/** Hekim onay kuyruğu — MDR human-in-the-loop merkezi ekran. */
export default function ApprovalsPage() {
  const [rows, setRows] = useState<
    { id: string; study_id: string; status: string; fusion_risk_score: number; created_at: string }[]
  >([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .listAnalyses("PENDING_REVIEW")
      .then(setRows)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <main className="container">
      <nav className="navbar" style={{ margin: "-24px -16px 16px", borderRadius: 8 }}>
        <Link href="/dashboard">← Panel</Link>
      </nav>
      <h1>Onay Bekleyen Analizler</h1>
      {error && <p style={{ color: "#c0392b" }}>{error}</p>}
      <div className="card">
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
            {rows.map((a) => (
              <tr key={a.id}>
                <td>{new Date(a.created_at).toLocaleString("tr-TR")}</td>
                <td style={{ color: a.fusion_risk_score >= 65 ? "#c0392b" : undefined }}>
                  {a.fusion_risk_score.toFixed(1)}
                </td>
                <td>
                  <span className="badge pending">⏳ Hekim onayı bekliyor</span>
                </td>
                <td>
                  <Link href={`/viewer/${a.study_id}?analysis=${a.id}`}>Değerlendir</Link>
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={4} style={{ color: "#8a93ab" }}>
                  Bekleyen analiz yok.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}
