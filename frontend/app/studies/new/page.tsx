"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, getTokens } from "../../../lib/api";
import {
  cleanDicom,
  cleanHea,
  hashAnonId,
  maskEpikriz,
  type DicomCleanReport,
  type HeaCleanReport,
  type PiiFinding,
} from "../../../lib/browser-anonymizer";

/**
 * KVKK vitrin ekranı: dosya seçildiği ANDA anonimizasyon istemcide koşar,
 * temizlenen alanlar canlı listelenir. Sunucuya yalnız anonim veri gider.
 */
export default function NewStudyPage() {
  const router = useRouter();
  const [modalityKind, setModalityKind] = useState<"image" | "ecg">("image");
  const [file, setFile] = useState<File | null>(null);
  const [heaFile, setHeaFile] = useState<File | null>(null);
  const [heaReport, setHeaReport] = useState<HeaCleanReport | null>(null);
  const [cleanedHeaText, setCleanedHeaText] = useState("");
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

  async function onEcgPicked(mat: File, hea: File | null) {
    setFile(mat);
    setHeaFile(hea);
    setHeaReport(null);
    setCleanedHeaText("");
    setError("");
    try {
      if (hea) {
        const text = await hea.text();
        const { text: cleaned, report } = await cleanHea(text, "pulsar-ecg-salt");
        setCleanedHeaText(cleaned);
        setHeaReport(report);
      }
      setAnonHash(await hashAnonId(`${mat.name}:${mat.size}:${mat.lastModified}`, "pulsar-ecg-salt"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "EKG dosyası işlenemedi");
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
        modality: modalityKind === "ecg" ? "ECG" : "CR",
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
      if (modalityKind === "ecg" && file) {
        const res = await api.analyzeEcgStudy(study.id, file, "signal.mat");
        analysisId = res.analysis_id;
      } else if (cleanedBytes) {
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
        <h3>1. Çalışma Türü</h3>
        <label style={{ marginRight: 18 }}>
          <input
            type="radio"
            checked={modalityKind === "ecg"}
            onChange={() => setModalityKind("ecg")}
          />{" "}
          EKG Kaydı (12 derivasyon, WFDB)
        </label>
        <label>
          <input
            type="radio"
            checked={modalityKind === "image"}
            onChange={() => setModalityKind("image")}
          />{" "}
          Radyoloji Görüntüsü (DICOM / PNG / JPEG)
        </label>
      </div>

      {modalityKind === "ecg" ? (
        <div className="card">
          <h3>2. EKG Sinyali (.mat + .hea)</h3>
          <p style={{ fontSize: 13, color: "#66708a" }}>
            PhysioNet WFDB formatı: <code>.mat</code> sinyal verisi (PHI içermez),
            <code> .hea</code> başlık dosyası (PHI içerebilir — tarayıcıda temizlenir,
            <strong> sunucuya asla gönderilmez</strong>).
          </p>
          <input
            type="file"
            accept=".mat"
            onChange={(e) => {
              const mat = e.target.files?.[0];
              if (mat) onEcgPicked(mat, heaFile);
            }}
          />{" "}
          <input
            type="file"
            accept=".hea"
            placeholder=".hea (opsiyonel)"
            onChange={(e) => {
              const hea = e.target.files?.[0];
              if (hea && file) onEcgPicked(file, hea);
            }}
          />
          {heaReport && (
            <div className="anon-panel">
              <strong>.hea Temizleme Raporu:</strong>
              <ul>
                {heaReport.recordPseudonym && (
                  <li className="anon-ok">✓ Kayıt kimliği → SHA256 pseudonym ({heaReport.recordPseudonym.slice(0, 8)}…)</li>
                )}
                {heaReport.ageBanded && <li className="anon-ok">✓ Yaş → {heaReport.ageBanded} bandına indirgendi</li>}
                {heaReport.sexRemoved && <li className="anon-ok">✓ Cinsiyet kaldırıldı</li>}
                {heaReport.maskedFields.map((t) => (
                  <li key={t} className="anon-ok">✓ Serbest metin maskelendi: {t}</li>
                ))}
                <li className="anon-ok">✓ Dx (teşhis) kodları korunur — klinik değer için zorunlu</li>
              </ul>
              {cleanedHeaText && (
                <>
                  <h4>Temizlenmiş başlık (sunucuya gitmez):</h4>
                  <pre style={{ background: "#f7f9fd", padding: 10, borderRadius: 8, fontSize: 12 }}>
                    {cleanedHeaText}
                  </pre>
                </>
              )}
            </div>
          )}
          {!heaReport && file && (
            <p className="anon-ok">✓ Sinyal hazır; .mat ikili verisi kimlik bilgisi taşımaz.</p>
          )}
        </div>
      ) : (
      <div className="card">
        <h3>2. Görüntü (DICOM / PNG / JPEG)</h3>
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
      )}

      <div className="card">
        <h3>3. Epikriz Metni</h3>
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
