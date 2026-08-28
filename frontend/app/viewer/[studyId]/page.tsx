"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import {
  api,
  getTokens,
  API_URL,
  type NlpResult,
  type VisionFinding,
  type VisionResult,
  type EcgResult,
} from "../../../lib/api";
import EcgPanel from "../../../components/EcgPanel";

/**
 * DICOM Viewer + XAI paneli.
 */
export default function ViewerPage() {
  const params = useParams<{ studyId: string }>();
  const search = useSearchParams();
  const studyId = params.studyId;
  const [analysisId, setAnalysisId] = useState<string | null>(search.get("analysis"));
  const [vision, setVision] = useState<VisionResult | null>(null);
  const [nlp, setNlp] = useState<NlpResult | null>(null);
  const [ecg, setEcg] = useState<EcgResult | null>(null);
  const [status, setStatus] = useState<string>("");
  const [riskScore, setRiskScore] = useState<number>(0);
  const [imgSrc, setImgSrc] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Yeni ozellikler
  const [prevStudies, setPrevStudies] = useState<{id:string; risk:number; status:string; modality:string; created_at:string; top_finding?:string|null}[]>([]);
  const [showPrev, setShowPrev] = useState(false);
  const [secondNote, setSecondNote] = useState("");
  const [secondBusy, setSecondBusy] = useState(false);
  const [secondSent, setSecondSent] = useState(false);
  const [criticalAlert, setCriticalAlert] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [pollTimer, setPollTimer] = useState<ReturnType<typeof setInterval> | null>(null);

  const loadAnalysis = useCallback(async (id: string) => {
    try {
      const a = await api.getAnalysis(id);
      setStatus(a.status);
      setRiskScore(a.fusion_risk_score);
      if (a.vision_result) {
        setVision(a.vision_result);
      }
      if (a.nlp_result) setNlp(a.nlp_result);
      if (a.ecg_result) {
        const { _file, ...ecgOut } = a.ecg_result as EcgResult & { _file?: string };
        setEcg(ecgOut);
      }
      // Kritik bulgu uyarisi
      if (a.fusion_risk_score >= 70) setCriticalAlert(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analiz yuklenemedi");
    }
  }, []);

  useEffect(() => {
    if (analysisId) {
      loadAnalysis(analysisId);
      return;
    }
    api
      .getStudy(studyId)
      .then((s) => {
        const latest = (s.analyses ?? [])[0];
        if (latest) setAnalysisId(latest.id);
        else setError("Bu calisma icin henuz analiz uretilmemis");
      })
      .catch(() => setError("Calisma yuklenemedi"));
  }, [analysisId, loadAnalysis, studyId]);

  // Analiz tamamlanana kadar 2 saniyede bir yenile
  useEffect(() => {
    if (status !== "PENDING_REVIEW" && !analyzing) {
      if (pollTimer) { clearInterval(pollTimer); setPollTimer(null); }
      return;
    }
    const timer = setInterval(() => {
      if (analysisId) loadAnalysis(analysisId);
    }, 2000);
    setPollTimer(timer);
    return () => clearInterval(timer);
  }, [status, analyzing, analysisId]);

  // Duz calisma goruntusu
  useEffect(() => {
    if (!analysisId || ecg) return;
    let alive = true;
    api
      .getCam(analysisId, { clean: true })
      .then((c) => {
        if (alive && c.cam_image_b64) {
          setImgSrc(`data:image/png;base64,${c.cam_image_b64}`);
        }
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [analysisId, ecg]);

  // Onceki tetkikleri yukle (ayni modaliteden)
  useEffect(() => {
    if (!studyId) return;
    api.listAnalyses().then((list) => {
      const items = list.filter((l) => l.study_id !== studyId).slice(0, 5);
      Promise.all(items.map(async (l) => {
        const s = await api.getStudy(l.study_id);
        return {
          id: l.study_id,
          risk: l.fusion_risk_score,
          status: l.status,
          modality: s.modality,
          created_at: l.created_at,
          top_finding: l.top_finding,
        };
      })).then(setPrevStudies).catch(() => {});
    }).catch(() => {});
  }, [studyId]);

  async function runAnalysis() {
    setBusy(true);
    setError("");
    try {
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

  async function downloadReport() {
    if (!analysisId) return;
    const tokens = getTokens();
    if (!tokens) return;
    setError("");
    try {
      const resp = await fetch(
        `${API_URL}/v1/analyses/${analysisId}/report.pdf`,
        { headers: { Authorization: `Bearer ${tokens.access_token}` } }
      );
      if (!resp.ok) throw new Error(`Rapor alinamadi (HTTP ${resp.status})`);
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `pulsar-rapor-${analysisId.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rapor indirilemedi");
    }
  }

  async function downloadPatientReport() {
    if (!analysisId) return;
    setError("");
    try {
      const blob = await api.getPatientReport(analysisId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `pulsar-hasta-rapor-${analysisId.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Hasta raporu indirilemedi");
    }
  }

  async function sendSecondOpinion() {
    if (!analysisId || !secondNote.trim()) return;
    setSecondBusy(true);
    try {
      await api.secondOpinion(analysisId, secondNote);
      setSecondSent(true);
      setSecondNote("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ikinci gorus gonderilemedi");
    } finally {
      setSecondBusy(false);
    }
  }

  const findings: VisionFinding[] = vision?.findings ?? [];
  const urgencyColor =
    nlp?.urgency === "yuksek" ? "#c0392b" : nlp?.urgency === "orta" ? "#b7791f" : "#1e8e4e";

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
          title={`risk katkisi: ${t.score.toFixed(2)}${t.negated ? " (negasyon)" : ""}`}
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
      {/* Kritik bulgu uyarisi */}
      {criticalAlert && (
        <div className="critical-alert">
          <span className="critical-alert-icon">&#9888;</span>
          <div>
            <strong>DIKKAT: Yuksek risk skoru</strong>
            <span>Fuzyon riski {riskScore.toFixed(1)}/100 — bu vaka yuksek oncelikle incelenmelidir.</span>
          </div>
          <button className="critical-alert-close" onClick={() => setCriticalAlert(false)}>&times;</button>
        </div>
      )}

      <nav className="navbar" style={{ margin: "-24px -16px 16px", borderRadius: 8 }}>
        <Link href="/dashboard">← Panel</Link>
        <span style={{ flex: 1 }} />
        {/* Onceki tetkik butonu */}
        {prevStudies.length > 0 && (
          <button className="btn secondary" style={{ marginRight: 8, padding: "4px 10px", fontSize: 12 }}
                  onClick={() => setShowPrev(!showPrev)}>
            Onceki Tetkikler ({prevStudies.length})
          </button>
        )}
        <Link href={`/present/${studyId}`} className="btn secondary" style={{ marginRight: 8, padding: "4px 10px", fontSize: 12 }}>
          ▶ Sunum Modu
        </Link>
        <span className={`badge ${status ? status.toLowerCase() : "loading"}`}>
          {status === ""
            ? "... YUKLENIYOR"
            : status === "PENDING_REVIEW"
              ? "⏳ HEKIM ONAYI BEKLIYOR"
              : status === "APPROVED"
                ? "✓ RAPOR KESINLESTI"
                : "✗ REDDEDILDI"}
        </span>
      </nav>

      {/* Analiz progress bar */}
      {analyzing && (
        <div style={{
          background: "#edf0f6", borderRadius: 8, padding: "12px 16px", marginBottom: 16,
          display: "flex", alignItems: "center", gap: 12,
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#2456d6" }}>Analiz calisiyor...</div>
            <div style={{ fontSize: 11, color: "#66708a" }}>AI Core sonuclari isliyor, lutfen bekleyin.</div>
          </div>
          <div style={{
            width: 120, height: 6, background: "#d1d9e6", borderRadius: 3, overflow: "hidden",
          }}>
            <div style={{
              height: "100%", background: "#2456d6", borderRadius: 3,
              animation: "progress-pulse 1.5s ease-in-out infinite",
              width: "60%",
            }} />
          </div>
          <style>{`@keyframes progress-pulse { 0%,100%{opacity:.4;width:40%} 50%{opacity:1;width:80%} }`}</style>
        </div>
      )}

      {/* Onceki tetkik karsilastirma paneli */}
      {showPrev && (
        <div className="card" style={{ marginBottom: 12, borderLeft: "3px solid #2456d6" }}>
          <h3 style={{ fontSize: 14, marginBottom: 8 }}>Onceki Tetkik Karsilastirmasi</h3>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {prevStudies.map((p) => (
              <Link key={p.id} href={`/viewer/${p.id}`}
                    style={{ flex: "1 1 140px", padding: 10, background: "#f5f7fb", borderRadius: 8, textDecoration: "none", border: "1px solid #e0e4ed" }}>
                <div style={{ fontSize: 12, color: "#66708a" }}>{p.modality} · {p.created_at.slice(0,10)}</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: p.risk >= 65 ? "#c0392b" : p.risk >= 35 ? "#d9a441" : "#1e8e4e" }}>
                  {p.risk.toFixed(1)}
                </div>
                <div style={{ fontSize: 11, color: "#8a93ab" }}>{p.top_finding || "Bulgu yok"}</div>
              </Link>
            ))}
          </div>
        </div>
      )}

      <h1>Analiz Goruntuleyici</h1>
      <p style={{ color: "#66708a" }}>
        Calisma: <code>{studyId.slice(0, 12)}...</code> · Fuzyon risk skoru:{" "}
        <strong style={{ fontSize: 18 }}>{riskScore.toFixed(1)}</strong>/100
      </p>
      {error && <p style={{ color: "#c0392b" }}>{error}</p>}

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        {/* ---- EKG Viewer + XAI ---- */}
        {ecg && analysisId && <EcgPanel result={ecg} analysisId={analysisId} />}

        {/* ---- Goruntu ---- */}
        {!ecg && (
        <div className="card viewer-image-card" style={{ flex: 2, minWidth: 380 }}>
          <h3>Goruntu</h3>
          {!imgSrc && (
            <div className="viewer-placeholder">
              Analiz verisi bekleniyor...
            </div>
          )}
          {imgSrc && (
            <div style={{ position: "relative", borderRadius: 8, overflow: "hidden" }}>
              <img src={imgSrc} alt="Calisma goruntusu" style={{ width: "100%", display: "block" }} />
            </div>
          )}

          <h4 style={{ marginBottom: 6 }}>Bulgu Listesi</h4>
          <table className="list">
            <thead>
              <tr><th>Bulgu</th><th>Olasilik</th></tr>
            </thead>
            <tbody>
              {(() => {
                const sorted = [...findings].sort((a, b) => b.probability - a.probability);
                const meaningful = sorted.filter((f) => f.probability >= 0.05);
                if (!sorted.length) {
                  return <tr><td colSpan={2} style={{ color: "#8a93ab" }}>Bulgu yok</td></tr>;
                }
                if (!meaningful.length) {
                  return <tr><td colSpan={2} style={{ color: "#8a93ab" }}>Belirgin bulgu saptanmadi (tum siniflarin olasiligi %5'in altinda).</td></tr>;
                }
                return meaningful.map((f) => (
                  <tr key={f.label}>
                    <td>{f.label}</td>
                    <td>
                      <div style={{ background: "#edf0f6", borderRadius: 6, width: 140, height: 10 }}>
                        <div style={{ width: `${Math.round(f.probability * 100)}%`, height: 10, borderRadius: 6, background: f.probability > 0.5 ? "#c0392b" : "#2456d6" }} />
                      </div>{" "}
                      <small>{(f.probability * 100).toFixed(1)}%</small>
                    </td>
                  </tr>
                ));
              })()}
            </tbody>
          </table>
        </div>
        )}

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
                  ({nlp.urgency_score}/100, guven {(nlp.confidence * 100).toFixed(0)}%)
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
            <h3>Hekim Karari (Zorunlu)</h3>
            <p style={{ fontSize: 13, color: "#66708a" }}>
              MDR human-in-the-loop: karar verilmeden rapor kesinlesmez.
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
                ✓ Rapor kesinlesti — degismez zaman damgasi audit loga yazildi.
              </p>
            )}
          </div>

          {/* PDF indirme butonlari */}
          <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
            <button className="btn" onClick={downloadPatientReport} disabled={busy}>
              📋 Hasta Raporu Indir
            </button>
            {(status === "APPROVED" || status === "REJECTED") && (
              <button className="btn" onClick={downloadReport} disabled={busy}>
                📄 Resmi Rapor PDF Indir
              </button>
            )}
          </div>

          {/* Ikinci hekim gorusu */}
          <div className="card" style={{ marginTop: 12, borderLeft: "3px solid #6b8cff" }}>
            <h3 style={{ fontSize: 14 }}>Ikinci Hekim Gorusu</h3>
            <p style={{ fontSize: 12, color: "#66708a", marginBottom: 8 }}>
              Baska bir hekimin gorusunu kaydedin (karari degistirmez, audit loga yazilir).
            </p>
            {secondSent ? (
              <p style={{ color: "#1e8e4e", fontSize: 13 }}>✓ Ikinci gorus kaydedildi.</p>
            ) : (
              <>
                <textarea
                  rows={2}
                  placeholder="Ikinci hekim gorus notu..."
                  value={secondNote}
                  onChange={(e) => setSecondNote(e.target.value)}
                  style={{ fontSize: 13 }}
                />
                <button className="btn secondary" onClick={sendSecondOpinion} disabled={secondBusy || !secondNote.trim()} style={{ marginTop: 6, fontSize: 12 }}>
                  👁 Ikinci Gorus Kaydet
                </button>
              </>
            )}
          </div>

          <button className="btn secondary" onClick={runAnalysis} disabled={busy} style={{ marginTop: 12 }}>
            Yenile
          </button>
        </div>
      </div>
    </main>
  );
}
