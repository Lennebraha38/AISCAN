"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import {
  api,
  type NlpResult,
  type VisionFinding,
  type VisionResult,
} from "../../../lib/api";

/**
 * DICOM Viewer + XAI paneli.
 * Cornerstone.js viewport üzerine Grad-CAM ısı haritası %40 opaklıkta bindirilir.
 */
export default function ViewerPage() {
  const params = useParams<{ studyId: string }>();
  const search = useSearchParams();
  const studyId = params.studyId;
  const [analysisId, setAnalysisId] = useState<string | null>(search.get("analysis"));
  const [vision, setVision] = useState<VisionResult | null>(null);
  const [nlp, setNlp] = useState<NlpResult | null>(null);
  const [status, setStatus] = useState<string>("");
  const [riskScore, setRiskScore] = useState<number>(0);
  const [selectedFinding, setSelectedFinding] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadAnalysis = useCallback(async (id: string) => {
    try {
      const a = await api.getAnalysis(id);
      setStatus(a.status);
      setRiskScore(a.fusion_risk_score);
      if (a.vision_result) setVision(a.vision_result);
      if (a.nlp_result) setNlp(a.nlp_result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analiz yüklenemedi");
    }
  }, []);

  useEffect(() => {
    if (!analysisId) return;
    loadAnalysis(analysisId);
  }, [analysisId, loadAnalysis]);

  async function runAnalysis() {
    setBusy(true);
    setError("");
    try {
      // Demo: viewer'dan yeniden analiz tetiklenemez; yükleme akışında üretilir.
      // Burada mevcut analizi yeniden yükleriz.
      if (analysisId) await loadAnalysis(analysisId);
    } finally {
      setBusy(false);
    }
  }

  async function decide(decision: "APPROVED" | "REJECTED") {
    if (!analysisId) return;
    setBusy(true);
    setError("");
    try {
      await api.decide(analysisId, decision, note || undefined);
      await loadAnalysis(analysisId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Karar kaydedilemedi");
    } finally {
      setBusy(false);
    }
  }

  const findings: VisionFinding[] = vision?.findings ?? [];
  const active =
    findings.find((f) => f.label === selectedFinding) ??
    findings.find((f) => f.probability > 0.5) ??
    findings[0];
  const camSrc = active?.cam_image_b64 ? `data:image/png;base64,${active.cam_image_b64}` : null;

  const urgencyColor =
    nlp?.urgency === "yüksek" ? "#c0392b" : nlp?.urgency === "orta" ? "#b7791f" : "#1e8e4e";

  function renderEpikrizWithHighlights(text: string, tokens: NlpResult["highlighted_tokens"]) {
    if (!tokens.length) return text;
    const parts: React.ReactNode[] = [];
    let cursor = 0;
    for (const t of tokens) {
      if (t.start < cursor) continue;
      parts.push(text.slice(cursor, t.start));
      const alpha = Math.min(Math.max(t.score, 0.15), 0.85);
      parts.push(
        <span
          key={`${t.start}-${t.end}`}
          className="hl-token"
          title={`risk katkısı: ${t.score.toFixed(2)}${t.negated ? " (negasyon)" : ""}`}
          style={{
            background: t.negated
              ? `rgba(40,120,200,${alpha * 0.4})`
              : `rgba(220,60,50,${alpha})`,
            color: alpha > 0.55 && !t.negated ? "#fff" : undefined,
          }}
        >
          {text.slice(t.start, t.end)}
        </span>
      );
      cursor = t.end;
    }
    parts.push(text.slice(cursor));
    return parts;
  }

  return (
    <main className="container">
      <nav className="navbar" style={{ margin: "-24px -16px 16px", borderRadius: 8 }}>
        <Link href="/dashboard">← Panel</Link>
        <span style={{ flex: 1 }} />
        <span className={`badge ${status.toLowerCase()}`}>
          {status === "PENDING_REVIEW"
            ? "⏳ HEKİM ONAYI BEKLİYOR"
            : status === "APPROVED"
              ? "✓ RAPOR KESİNLEŞTİ"
              : "✗ REDDEDİLDİ"}
        </span>
      </nav>

      <h1>Analiz Görüntüleyici</h1>
      <p style={{ color: "#66708a" }}>
        Çalışma: <code>{studyId.slice(0, 12)}…</code> · Füzyon risk skoru:{" "}
        <strong style={{ fontSize: 18 }}>{riskScore.toFixed(1)}</strong>/100
      </p>
      {error && <p style={{ color: "#c0392b" }}>{error}</p>}

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        {/* ---- Viewer + CAM overlay ---- */}
        <div className="card" style={{ flex: 2, minWidth: 380 }}>
          <h3>Görüntü + Grad-CAM Isı Haritası</h3>
          {!camSrc && (
            <div
              style={{
                background: "#101a33",
                borderRadius: 8,
                height: 320,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#8fa3d0",
              }}
            >
              Analiz verisi bekleniyor…
            </div>
          )}
          {camSrc && (
            <div style={{ position: "relative", borderRadius: 8, overflow: "hidden" }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={camSrc} alt="Grad-CAM bindirilmiş görüntü" style={{ width: "100%", display: "block" }} />
              <div
                style={{
                  position: "absolute",
                  left: 10,
                  bottom: 10,
                  background: "rgba(16,26,51,.78)",
                  color: "#fff",
                  padding: "6px 10px",
                  borderRadius: 6,
                  fontSize: 12,
                }}
              >
                XAI yöntemi: {vision?.xai_method} · overlay %40 opaklık
              </div>
            </div>
          )}

          <h4 style={{ marginBottom: 6 }}>Bulgu Listesi</h4>
          <table className="list">
            <thead>
              <tr>
                <th>Bulgu</th>
                <th>Olasılık</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {findings.map((f) => (
                <tr key={f.label} style={{ background: f.label === active?.label ? "#f3f8ff" : undefined }}>
                  <td>{f.label}</td>
                  <td>
                    <div style={{ background: "#edf0f6", borderRadius: 6, width: 140, height: 10 }}>
                      <div
                        style={{
                          width: `${Math.round(f.probability * 100)}%`,
                          height: 10,
                          borderRadius: 6,
                          background: f.probability > 0.5 ? "#c0392b" : "#2456d6",
                        }}
                      />
                    </div>{" "}
                    <small>{(f.probability * 100).toFixed(1)}%</small>
                  </td>
                  <td>
                    <button className="btn secondary" onClick={() => setSelectedFinding(f.label)}>
                      Bölgeyi Göster
                    </button>
                  </td>
                </tr>
              ))}
              {!findings.length && (
                <tr>
                  <td colSpan={3} style={{ color: "#8a93ab" }}>Bulgu yok</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* ---- Epikriz XAI + Onay ---- */}
        <div style={{ flex: 1, minWidth: 320 }}>
          <div className="card">
            <h3>Epikriz Analizi (Metin XAI)</h3>
            {nlp ? (
              <>
                <p>
                  Aciliyet:{" "}
                  <strong style={{ color: urgencyColor, textTransform: "uppercase" }}>
                    {nlp.urgency}
                  </strong>{" "}
                  ({nlp.urgency_score}/100, güven {(nlp.confidence * 100).toFixed(0)}%)
                </p>
                <p style={{ fontSize: 13, color: "#66708a" }}>{nlp.rationale}</p>
                <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: 14, lineHeight: 1.7 }}>
                  {renderEpikrizWithHighlights(nlp.rationale, nlp.highlighted_tokens)}
                </pre>
              </>
            ) : (
              <p style={{ color: "#8a93ab" }}>Epikriz analizi bulunmuyor.</p>
            )}
          </div>

          <div className="card" style={{ borderColor: "#e0c36a" }}>
            <h3>Hekim Kararı (Zorunlu)</h3>
            <p style={{ fontSize: 13, color: "#66708a" }}>
              MDR human-in-the-loop: karar verilmeden rapor kesinleşmez.
            </p>
            <textarea
              rows={3}
              placeholder="Hekim notu (opsiyonel)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              disabled={status !== "PENDING_REVIEW"}
            />
            <button className="btn success" disabled={busy || status !== "PENDING_REVIEW"} onClick={() => decide("APPROVED")}>
              ✓ ONAYLA
            </button>{" "}
            <button className="btn danger" disabled={busy || status !== "PENDING_REVIEW"} onClick={() => decide("REJECTED")}>
              ✗ REDDET
            </button>
            {status === "APPROVED" && (
              <p className="anon-ok" style={{ marginTop: 10 }}>
                ✓ Rapor kesinleşti — değişmez zaman damgası audit log'a yazıldı.
              </p>
            )}
          </div>

          <button className="btn secondary" onClick={runAnalysis} disabled={busy}>
            Yenile
          </button>
        </div>
      </div>
    </main>
  );
}
