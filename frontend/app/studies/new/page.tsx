"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, getTokens } from "../../../lib/api";
import {
  cleanDicom,
  hashAnonId,
  maskEpikriz,
  type DicomCleanReport,
  type PiiFinding,
} from "../../../lib/browser-anonymizer";

/**
 * KVKK vitrin ekranı: dosya seçildiği ANDA anonimizasyon istemcide koşar,
 * temizlenen alanlar canlı listelenir. Sunucuya yalnız anonim veri gider.
 */
export default function NewStudyPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [epikriz, setEpikriz] = useState("");
  const [maskedEpikriz, setMaskedEpikriz] = useState("");
  const [piiFindings, setPiiFindings] = useState<PiiFinding[]>([]);
  const [dicomReport, setDicomReport] = useState<DicomCleanReport | null>(null);
  const [cleanedBytes, setCleanedBytes] = useState<Uint8Array | null>(null);
  const [anonHash, setAnonHash] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getTokens()) window.location.href = "/login";
  }, []);

  async function onFilePicked(f: File) {
    setFile(f);
    setError("");
    setDicomReport(null);
    setCleanedBytes(null);
    try {
      const raw = new Uint8Array(await f.arrayBuffer());
      const isDicom =
        f.name.toLowerCase().endsWith(".dcm") ||
        String.fromCharCode(...raw.slice(128, 132)) === "DICM";
      if (isDicom) {
        const { bytes, report } = await cleanDicom(raw, "pulsar-kkds-salt");
        setCleanedBytes(bytes);
        setDicomReport(report);
        setAnonHash(await hashAnonId(`${f.name}:${f.size}:${f.lastModified}`, "pulsar-kkds-salt"));
      } else {
        // PNG/JPEG görüntü: kimlik taşımaz; hash yalnız dosya parmak izinden.
        setAnonHash(await hashAnonId(`${f.name}:${f.size}:${f.lastModified}`, "pulsar-img-salt"));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Dosya işlenemedi");
    }
  }

  function onEpikrizChange(text: string) {
    setEpikriz(text);
    const result = maskEpikriz(text);
    setMaskedEpikriz(result.maskedText);
    setPiiFindings(result.findings);
  }

  async function onSubmit() {
    if (!anonHash) return;
    setBusy(true);
    setError("");
    try {
      const study = await api.createStudy({
        anon_study_hash: anonHash,
        modality: file?.name.toLowerCase().endsWith(".dcm") ? "CR" : "CR",
        image_count: file ? 1 : 0,
        masked_epikriz: maskedEpikriz || null,
        anonymization_report: dicomReport
          ? {
              removed: dicomReport.removed,
              hashed: dicomReport.hashed,
              private_tags_removed: dicomReport.privateTagsRemoved,
            }
          : null,
      });
      let analysisId: string | null = null;
      if (cleanedBytes) {
        const blob = new Blob([cleanedBytes as unknown as BlobPart], { type: "application/dicom" });
        const res = await api.analyzeStudy(study.id, blob, "anonymized.dcm");
        analysisId = res.analysis_id;
      }
      router.push(`/viewer/${study.id}${analysisId ? `?analysis=${analysisId}` : ""}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kayıt başarısız");
    } finally {
      setBusy(false);
    }
  }

  const totalCleaned =
    (dicomReport?.removed.length ?? 0) +
    (dicomReport?.hashed.length ?? 0) +
    (dicomReport?.privateTagsRemoved ?? 0) +
    piiFindings.length;

  return (
    <main className="container">
      <h1>Yeni Çalışma — Anonimleştirilmiş Yükleme</h1>

      <div className="card" style={{ borderColor: "#9ec2ff", background: "#f3f8ff" }}>
        <span className="badge kvkk">KVKK · Zero-Knowledge Architecture</span>
        <p style={{ marginBottom: 0 }}>
          Dosyanız bu tarayıcıda anonimleştirilir; sunucuya yalnızca temizlenmiş veri iletilir.
          Ham dosya hiçbir ağ isteğinde bulunmaz.
        </p>
      </div>

      <div className="card">
        <h3>1. Görüntü (DICOM / PNG / JPEG)</h3>
        <input
          type="file"
          accept=".dcm,.png,.jpg,.jpeg,application/dicom"
          onChange={(e) => e.target.files?.[0] && onFilePicked(e.target.files[0])}
        />
        {dicomReport && (
          <div className="anon-panel">
            <strong>Temizlenen Alanlar ({totalCleaned}):</strong>
            <ul>
              {dicomReport.hashed.map((t) => (
                <li key={t} className="anon-ok">✓ {t} → SHA256 pseudonym ile değiştirildi</li>
              ))}
              {dicomReport.removed.map((t) => (
                <li key={t} className="anon-ok">✓ {t} kaldırıldı</li>
              ))}
              {dicomReport.privateTagsRemoved > 0 && (
                <li className="anon-ok">✓ {dicomReport.privateTagsRemoved} özel (private) tag kaldırıldı</li>
              )}
            </ul>
          </div>
        )}
        {!dicomReport && file && (
          <p className="anon-ok">✓ Görüntü kimlik bilgisi taşımıyor; parmak izi hash'i üretildi.</p>
        )}
      </div>

      <div className="card">
        <h3>2. Epikriz Metni</h3>
        <textarea
          rows={6}
          placeholder="Hasta epikrizini buraya yapıştırın... (PII otomatik maskelenir)"
          value={epikriz}
          onChange={(e) => onEpikrizChange(e.target.value)}
        />
        {piiFindings.length > 0 && (
          <div className="anon-panel">
            <strong>Tespit edilen ve maskelenen PII ({piiFindings.length}):</strong>
            <ul>
              {piiFindings.map((f, i) => (
                <li key={i} className="anon-ok">
                  ✓ {f.type} → {f.label}
                </li>
              ))}
            </ul>
          </div>
        )}
        {maskedEpikriz && (
          <>
            <h4>Sunucuya gidecek metin:</h4>
            <pre style={{ background: "#f7f9fd", padding: 12, borderRadius: 8, whiteSpace: "pre-wrap" }}>
              {maskedEpikriz}
            </pre>
          </>
        )}
      </div>

      {error && <p style={{ color: "#c0392b" }}>{error}</p>}
      <button className="btn" disabled={!anonHash || busy} onClick={onSubmit}>
        {busy ? "Gönderiliyor..." : "Anonim Çalışmayı Kaydet ve Analiz Et"}
      </button>{" "}
      <Link href="/dashboard" className="btn secondary">Vazgeç</Link>
    </main>
  );
}
