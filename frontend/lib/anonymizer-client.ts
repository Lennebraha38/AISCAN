/**
 * Pulsar-KKDS istemci tarafı anonimizasyon köprüsü.
 *
 * KVKK / Zero-Knowledge Architecture:
 * Bu modül tarayıcıda çalışır; dosya seçildiği anda DICOM metadata temizliği
 * ve epikriz PII maskesi BURADA yapılır. Sunucuya yalnızca anonimleştirilmiş
 * çıktı gönderilir (ham dosya hiçbir HTTP isteğinin body'sine girmez).
 *
 * Birincil yol: lib/browser-anonymizer.ts (TypeScript portu).
 * Yükseltme yolu: Rust/WASM paketi derlendiğinde aynı arayüzle takas edilir
 * (bkz. anonymizer/dicom_cleaner/wasm/README.md).
 */

export interface AnonymizationReport {
  removed: string[];
  hashed: string[];
  privateTagsRemoved: number;
}

export interface PiiFinding {
  type: string;
  start: number;
  end: number;
  label: string;
}

export interface EpikrizMaskResult {
  maskedText: string;
  findings: PiiFinding[];
  piiCount: number;
}

export { cleanDicom as cleanDicomWasmReady, hashAnonId } from "./browser-anonymizer";

import {
  cleanDicom,
  maskEpikriz,
  type DicomCleanReport,
} from "./browser-anonymizer";

/** DICOM byte stream'ini istemcide anonimleştirir. */
export async function cleanDicomInBrowser(
  fileBytes: Uint8Array,
  salt: string
): Promise<{ bytes: Uint8Array; report: AnonymizationReport }> {
  const result = await cleanDicom(fileBytes, salt);
  const report: DicomCleanReport = result.report;
  return {
    bytes: result.bytes,
    report: {
      removed: report.removed,
      hashed: report.hashed,
      privateTagsRemoved: report.privateTagsRemoved,
    },
  };
}

/** Türkçe epikriz metnini istemcide maskeler ([TC_KIMLIK] vb. etiketlerle). */
export async function maskEpikrizInBrowser(text: string): Promise<EpikrizMaskResult> {
  const r = maskEpikriz(text);
  return { maskedText: r.maskedText, findings: r.findings, piiCount: r.findings.length };
}

/** Backend'in kabul ettiği formattaki şeffaflık raporu. */
export function toServerReport(report: AnonymizationReport): Record<string, unknown> {
  return {
    removed: report.removed,
    hashed: report.hashed,
    private_tags_removed: report.privateTagsRemoved,
  };
}
