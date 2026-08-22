"use client";

import { useEffect, useRef, useState } from "react";
import { api, type EcgResult, type EcgSignal } from "../lib/api";

const LEAD_LABELS_TR: Record<string, string> = {
  I: "I", II: "II", III: "III", aVR: "aVR", aVL: "aVL", aVF: "aVF",
};

const CLASS_TR: Record<string, string> = {
  normal: "NORMAL EKG",
  arrhythmia: "RİTİM BOZUKLUĞU",
  block: "İLETİM BOZUKLUĞU",
};

const CLASS_COLOR: Record<string, string> = {
  normal: "#1e8e4e",
  arrhythmia: "#c0392b",
  block: "#b7791f",
};

function heatColor(v: number): string {
  // 0 -> seffaf, 1 -> kirmizi; sarı ara bölge
  const a = Math.min(Math.max(v, 0), 1);
  if (a < 0.5) return `rgba(255,196,0,${a * 1.2})`;
  return `rgba(220,50,40,${0.35 + a * 0.6})`;
}

/**
 * 12 derivasyonlu EKG görüntüleyici + 1D XAI katmanları.
 * - Dalga formları backend'den alınan gerçek sinyal verisidir.
 * - grad_cam: zaman ekseninde karar odağını gösteren ısı şeridi.
 * - lead_saliency: derivasyon bazlı önem (etiket rengi yoğunluğu).
 */
export default function EcgPanel({ result, analysisId }: { result: EcgResult; analysisId: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [signal, setSignal] = useState<EcgSignal | null>(null);
  const [err, setErr] = useState("");
  const [showCam, setShowCam] = useState(true);

  useEffect(() => {
    let alive = true;
    api
      .getEcgSignal(analysisId)
      .then((s) => alive && setSignal(s))
      .catch((e) => alive && setErr(e instanceof Error ? e.message : "Sinyal yüklenemedi"));
    return () => {
      alive = false;
    };
  }, [analysisId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !signal) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width;
    const rowH = canvas.height / 12;
    ctx.fillStyle = "#0d1428";
    ctx.fillRect(0, 0, W, canvas.height);

    const n = signal.samples;
    const cams = showCam && result.grad_cam?.length ? result.grad_cam : null;

    for (let l = 0; l < 12; l++) {
      const y0 = l * rowH;
      const lead = signal.signal[l] ?? [];
      const peak = Math.max(1e-6, ...lead.map((v) => Math.abs(v)));

      // saliency arka plan (derivasyon bazlı)
      const salRow = result.lead_saliency?.[l] ?? [];
      if (showCam && salRow.length) {
        for (let i = 0; i < salRow.length; i++) {
          const v = salRow[i];
          if (v > 0.25) {
            ctx.fillStyle = `rgba(36,86,214,${Math.min(v * 0.35, 0.4)})`;
            ctx.fillRect((i / salRow.length) * W, y0, W / salRow.length + 1, rowH);
          }
        }
      }

      // zaman ekseni CAM şeridi (tum derivasyonlara ortak karar odagi)
      if (cams) {
        const colW = W / cams.length;
        for (let i = 0; i < cams.length; i++) {
          const v = cams[i];
          if (v > 0.18) {
            ctx.fillStyle = heatColor(v);
            ctx.fillRect(i * colW, y0, colW + 1, rowH);
          }
        }
      }

      // dalga formu
      ctx.strokeStyle = "#7ef7c6";
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      for (let i = 0; i < lead.length; i++) {
        const x = (i / Math.max(1, lead.length - 1)) * W;
        const y = y0 + rowH / 2 - (lead[i] / peak) * (rowH * 0.38);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // izolasyon cizgisi + etiket
      ctx.strokeStyle = "rgba(120,140,190,.25)";
      ctx.beginPath();
      ctx.moveTo(0, y0 + rowH);
      ctx.lineTo(W, y0 + rowH);
      ctx.stroke();
      const label = LEAD_LABELS_TR[signal.leads[l]] ?? signal.leads[l];
      ctx.fillStyle = "#c9d6f5";
      ctx.font = "11px monospace";
      ctx.fillText(label, 6, y0 + 14);
    }
  }, [signal, result, showCam]);

  const clsColor = CLASS_COLOR[result.superclass] ?? "#666";
  const probs = Object.entries(result.probabilities).sort((a, b) => b[1] - a[1]);

  return (
    <div className="card" style={{ flex: 2, minWidth: 380 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <h3 style={{ margin: 0 }}>12-Derivasyonlu EKG + XAI Katmanı</h3>
        <label style={{ fontSize: 13, display: "flex", gap: 4, alignItems: "center" }}>
          <input type="checkbox" checked={showCam} onChange={(e) => setShowCam(e.target.checked)} />
          XAI katmanı
        </label>
      </div>

      <div
        style={{
          margin: "10px 0",
          padding: "8px 12px",
          borderRadius: 8,
          background: `${clsColor}1a`,
          border: `1px solid ${clsColor}55`,
          display: "flex",
          gap: 16,
          flexWrap: "wrap",
          alignItems: "baseline",
        }}
      >
        <strong style={{ color: clsColor, fontSize: 16 }}>
          {CLASS_TR[result.superclass] ?? result.superclass}
        </strong>
        <span style={{ fontSize: 13, color: "#66708a" }}>
          güven %{(result.confidence * 100).toFixed(1)}
          {result.heart_rate_bpm ? <> · KHD {result.heart_rate_bpm.toFixed(0)} bpm</> : null}
          {" · "}
          {result.backend}
        </span>
      </div>

      {err && <p style={{ color: "#c0392b" }}>{err}</p>}
      {!signal && !err && (
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
          Sinyal yükleniyor…
        </div>
      )}
      <canvas
        ref={canvasRef}
        width={920}
        height={760}
        style={{ width: "100%", borderRadius: 8, display: signal ? "block" : "none" }}
      />
      {signal && (
        <p style={{ fontSize: 12, color: "#8a93ab", marginTop: 6 }}>
          Kırmızı/sarı şerit: modelin karar odağı (Grad-CAM 1D) · mavi zemin: derivasyon önemi ·{" "}
          {signal.fs_effective} Hz örnekleme, {signal.samples} örnek
        </p>
      )}

      <h4 style={{ marginBottom: 6 }}>Sınıf Olasılıkları</h4>
      <table className="list">
        <tbody>
          {probs.map(([k, v]) => (
            <tr key={k}>
              <td>{CLASS_TR[k] ?? k}</td>
              <td>
                <div style={{ background: "#edf0f6", borderRadius: 6, width: 160, height: 10 }}>
                  <div
                    style={{
                      width: `${Math.round(v * 100)}%`,
                      height: 10,
                      borderRadius: 6,
                      background: CLASS_COLOR[k] ?? "#2456d6",
                    }}
                  />
                </div>{" "}
                <small>{(v * 100).toFixed(1)}%</small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {result.rationale && (
        <p style={{ fontSize: 13, color: "#66708a", marginTop: 8 }}>
          Gerekçe: {result.rationale}
        </p>
      )}
    </div>
  );
}
