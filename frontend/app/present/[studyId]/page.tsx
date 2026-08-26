"use client";
/**
 * Sunum Modu — tam ekran vaka-vaka yuruyen juri sunumu.
 *
 * Klavye: ←/→ veya ↑/↓ ile vaka degistirme, Esc ile cikis.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, type VisionFinding, type VisionResult, type NlpResult, type EcgResult } from "../../../lib/api";

interface Slide {
  studyId: string;
  analysisId: string;
  riskScore: number;
  status: string;
  modality?: string | null;
  topFinding?: string | null;
  vision?: VisionResult | null;
  nlp?: NlpResult | null;
  ecg?: EcgResult | null;
  imgSrc?: string | null;
}

export default function PresentPage() {
  const params = useParams<{ studyId: string }>();
  const router = useRouter();
  const [slides, setSlides] = useState<Slide[]>([]);
  const [idx, setIdx] = useState(0);
  const [loading, setLoading] = useState(true);

  // Tum analizleri yukle
  const loadAll = useCallback(async () => {
    try {
      const list = await api.listAnalyses();
      const result: Slide[] = [];
      for (const item of list) {
        try {
          const a = await api.getAnalysis(item.id);
          let imgSrc: string | null = null;
          if (!a.ecg_result) {
            try {
              const cam = await api.getCam(a.id, { clean: true });
              if (cam.cam_image_b64) imgSrc = `data:image/png;base64,${cam.cam_image_b64}`;
            } catch {}
          }
          const { _file, ...ecgOut } = (a.ecg_result || {}) as EcgResult & { _file?: string };
          result.push({
            studyId: item.study_id,
            analysisId: a.id,
            riskScore: a.fusion_risk_score,
            status: a.status,
            modality: item.modality,
            topFinding: item.top_finding,
            vision: a.vision_result,
            nlp: a.nlp_result,
            ecg: Object.keys(ecgOut).length ? ecgOut : null,
            imgSrc,
          });
        } catch {}
      }
      setSlides(result);
      // Baslangiç indeksini bul
      const startIdx = result.findIndex((s) => s.studyId === params.studyId);
      if (startIdx >= 0) setIdx(startIdx);
    } finally {
      setLoading(false);
    }
  }, [params.studyId]);

  useEffect(() => { loadAll(); }, [loadAll]);

  // Klavye navigasyonu
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        e.preventDefault();
        setIdx((i) => Math.min(i + 1, slides.length - 1));
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault();
        setIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === "Escape") {
        router.push(`/viewer/${params.studyId}`);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [slides, params.studyId, router]);

  // Tam ekran
  useEffect(() => {
    document.documentElement.requestFullscreen?.().catch(() => {});
    return () => { document.exitFullscreen?.().catch(() => {}); };
  }, []);

  const slide = slides[idx];
  if (loading) {
    return (
      <div style={{ background: "#0a0f1e", color: "#fff", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <p style={{ fontSize: 20 }}>Vakalar yukleniyor...</p>
      </div>
    );
  }

  if (!slide) {
    return (
      <div style={{ background: "#0a0f1e", color: "#fff", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 16 }}>
        <p style={{ fontSize: 20 }}>Gosterilecek vaka bulunamadi</p>
        <button onClick={() => router.push("/dashboard")} style={{ padding: "12px 24px", background: "#2456d6", color: "#fff", border: "none", borderRadius: 8, fontSize: 16, cursor: "pointer" }}>
          Panele Don
        </button>
      </div>
    );
  }

  const findings = slide.vision?.findings ?? [];
  const sorted = [...findings].sort((a, b) => b.probability - a.probability).filter((f) => f.probability >= 0.05);
  const riskColor = slide.riskScore >= 65 ? "#c0392b" : slide.riskScore >= 35 ? "#d9a441" : "#2e9e5b";

  return (
    <div style={{ background: "#0a0f1e", color: "#fff", minHeight: "100vh", padding: 32, display: "flex", flexDirection: "column" }}>
      {/* Ust bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, opacity: 0.7 }}>
        <span style={{ fontSize: 13 }}>Pulsar-KKDS Sunum Modu</span>
        <span style={{ fontSize: 13 }}>{idx + 1} / {slides.length}</span>
        <Link href={`/viewer/${slide.studyId}`} style={{ color: "#6b8cff", fontSize: 13, textDecoration: "none" }}>
          Viewer'a Don (Esc)
        </Link>
      </div>

      {/* Ana icerik */}
      <div style={{ display: "flex", gap: 24, flex: 1, minHeight: 0 }}>
        {/* Sol: Goruntu */}
        <div style={{ flex: 3, display: "flex", alignItems: "center", justifyContent: "center", background: "#101832", borderRadius: 12, overflow: "hidden", minHeight: 300 }}>
          {slide.ecg ? (
            <div style={{ padding: 24, textAlign: "center" }}>
              <p style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>{slide.ecg.superclass.toUpperCase()}</p>
              <p style={{ fontSize: 16, color: "#8fa3d0" }}>Guven: {(slide.ecg.confidence * 100).toFixed(0)}%</p>
              {slide.ecg.heart_rate_bpm && <p style={{ fontSize: 16, color: "#8fa3d0" }}>Nabiz: {slide.ecg.heart_rate_bpm.toFixed(0)} bpm</p>}
            </div>
          ) : slide.imgSrc ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={slide.imgSrc} alt="Calismma" style={{ maxHeight: "80vh", maxWidth: "100%", objectFit: "contain" }} />
          ) : (
            <p style={{ color: "#4a5578" }}>Goruntu yuklenemedi</p>
          )}
        </div>

        {/* Sag: Bulgular + Risk */}
        <div style={{ flex: 2, display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Risk */}
          <div style={{ background: "#141d35", borderRadius: 12, padding: 20, borderLeft: `4px solid ${riskColor}` }}>
            <p style={{ fontSize: 13, color: "#8a93ab", marginBottom: 4 }}>FUZYON RISK SKORU</p>
            <p style={{ fontSize: 48, fontWeight: 800, color: riskColor, margin: 0 }}>{slide.riskScore.toFixed(1)}</p>
            <div style={{ background: "#1e2a48", borderRadius: 8, height: 8, marginTop: 8 }}>
              <div style={{ width: `${slide.riskScore}%`, height: 8, borderRadius: 8, background: riskColor }} />
            </div>
          </div>

          {/* Modality + bulgu */}
          <div style={{ background: "#141d35", borderRadius: 12, padding: 16 }}>
            <p style={{ fontSize: 12, color: "#8a93ab", marginBottom: 4 }}>MODALITE</p>
            <p style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>{slide.modality || "-"}</p>
            {slide.topFinding && <p style={{ fontSize: 14, color: "#6b8cff", marginTop: 4 }}>Baskin bulgu: {slide.topFinding}</p>}
          </div>

          {/* Bulgular */}
          <div style={{ background: "#141d35", borderRadius: 12, padding: 16, flex: 1, overflow: "auto" }}>
            <p style={{ fontSize: 12, color: "#8a93ab", marginBottom: 8 }}>BULGULAR</p>
            {sorted.length ? sorted.map((f) => (
              <div key={f.label} style={{ marginBottom: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 2 }}>
                  <span>{f.label}</span>
                  <span style={{ color: f.probability > 0.5 ? "#c0392b" : "#6b8cff", fontWeight: 600 }}>
                    {(f.probability * 100).toFixed(1)}%
                  </span>
                </div>
                <div style={{ background: "#1e2a48", borderRadius: 4, height: 5 }}>
                  <div style={{ width: `${f.probability * 100}%`, height: 5, borderRadius: 4, background: f.probability > 0.5 ? "#c0392b" : "#2456d6" }} />
                </div>
              </div>
            )) : (
              <p style={{ color: "#4a5578", fontSize: 13 }}>Belirgin bulgu saptanmadi</p>
            )}
          </div>

          {/* NLP */}
          {slide.nlp && (
            <div style={{ background: "#141d35", borderRadius: 12, padding: 12 }}>
              <span style={{ fontSize: 12, color: "#8a93ab" }}>Aciliyet: </span>
              <span style={{ fontSize: 14, fontWeight: 700, color: slide.nlp.urgency === "yuksek" ? "#c0392b" : slide.nlp.urgency === "orta" ? "#d9a441" : "#2e9e5b", textTransform: "uppercase" as const }}>
                {slide.nlp.urgency}
              </span>
              <span style={{ fontSize: 12, color: "#8a93ab", marginLeft: 8 }}>({slide.nlp.urgency_score}/100)</span>
            </div>
          )}
        </div>
      </div>

      {/* Alt navigasyon cubugu */}
      <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 16, opacity: 0.6 }}>
        {slides.map((_, i) => (
          <button
            key={i}
            onClick={() => setIdx(i)}
            style={{
              width: i === idx ? 32 : 12, height: 12, borderRadius: 6,
              background: i === idx ? "#2456d6" : "#2a3558",
              border: "none", cursor: "pointer", transition: "all 0.2s",
            }}
          />
        ))}
      </div>
    </div>
  );
}
