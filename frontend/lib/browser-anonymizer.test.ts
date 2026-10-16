import { beforeEach, describe, expect, it } from "vitest";
import {
  cleanDicom,
  cleanHea,
  getOrCreateAnonSalt,
  hashAnonId,
  maskEpikriz,
} from "./browser-anonymizer";

const SALT = "test-salt-0123456789abcdef";

// ---------------------------------------------------------------------------
// DICOM üretici yardımcıları (explicit/implicit VR Little Endian)
// ---------------------------------------------------------------------------

const LONG_VRS = ["OB", "OD", "OF", "OL", "OV", "OW", "SQ", "UC", "UR", "UT", "UN"];

function elemExplicit(
  group: number,
  element: number,
  vr: string,
  value: string | Uint8Array
): Uint8Array {
  const raw = typeof value === "string" ? new TextEncoder().encode(value) : value;
  const pad = raw.length % 2 ? 1 : 0;
  const len = raw.length + pad;
  const isLong = LONG_VRS.includes(vr);
  const headerLen = isLong ? 12 : 8;
  const buf = new Uint8Array(headerLen + len);
  const view = new DataView(buf.buffer);
  view.setUint16(0, group, true);
  view.setUint16(2, element, true);
  buf[4] = vr.charCodeAt(0);
  buf[5] = vr.charCodeAt(1);
  if (isLong) {
    view.setUint16(6, 0, true);
    view.setUint32(8, len, true);
  } else {
    view.setUint16(6, len, true);
  }
  buf.set(raw, headerLen);
  return buf;
}

function elemImplicit(group: number, element: number, value: string | Uint8Array): Uint8Array {
  const raw = typeof value === "string" ? new TextEncoder().encode(value) : value;
  const pad = raw.length % 2 ? 1 : 0;
  const buf = new Uint8Array(8 + raw.length + pad);
  const view = new DataView(buf.buffer);
  view.setUint16(0, group, true);
  view.setUint16(2, element, true);
  view.setUint32(4, raw.length + pad, true);
  buf.set(raw, 8);
  return buf;
}

function concat(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(total);
  let off = 0;
  for (const p of parts) {
    out.set(p, off);
    off += p.length;
  }
  return out;
}

function filePreamble(): Uint8Array[] {
  return [new Uint8Array(128), new TextEncoder().encode("DICM")];
}

function buildExplicitDicom(): Uint8Array {
  return concat([
    ...filePreamble(),
    elemExplicit(0x0002, 0x0010, "UI", "1.2.840.10008.1.2.1"), // Explicit VR LE
    elemExplicit(0x0010, 0x0010, "PN", "DOE^JOHN"), // hash
    elemExplicit(0x0010, 0x0020, "LO", "PID-42"), // hash
    elemExplicit(0x0008, 0x0080, "LO", "Hospital X"), // remove
    elemExplicit(0x0010, 0x0040, "CS", "M"), // remove
    elemExplicit(0x0011, 0x0010, "LO", "PRIVATE"), // özel etiket -> remove
    elemExplicit(0x7FE0, 0x0010, "OW", new Uint8Array([1, 2, 3, 4])), // piksel korunur
  ]);
}

function buildImplicitDicom(): Uint8Array {
  return concat([
    ...filePreamble(),
    elemExplicit(0x0002, 0x0010, "UI", "1.2.840.10008.1.2"), // Implicit VR LE
    elemImplicit(0x0010, 0x0010, "DOE^JOHN"),
    elemImplicit(0x0010, 0x0040, "M"),
    elemImplicit(0x0008, 0x0080, "Hospital X"),
    elemImplicit(0x7FE0, 0x0010, new Uint8Array([9, 8, 7, 6])),
  ]);
}

// ---------------------------------------------------------------------------

describe("maskEpikriz", () => {
  it("geçerli TC kimliği maskeler, geçersiz checksum'lıyı korur", () => {
    const r = maskEpikriz("T.C. Kimlik No 10000000146 ve 12345678901");
    expect(r.maskedText).toContain("[TC_KIMLIK]");
    expect(r.maskedText).not.toContain("10000000146");
    // Geçersiz TC maskelenmez (false positive engeli).
    expect(r.maskedText).toContain("12345678901");
  });

  it("demo epikrizinde kişi adı ve TC birlikte maskelenir (e2e paritesi)", () => {
    const r = maskEpikriz(
      "Hasta AHMET YILMAZ, T.C. Kimlik No 10000000146. Toraks BT'de nodül."
    );
    expect(r.maskedText).toContain("[KISI_ADI]");
    expect(r.maskedText).toContain("[TC_KIMLIK]");
    expect(r.maskedText).not.toContain("AHMET YILMAZ");
    expect(r.maskedText).not.toContain("10000000146");
  });

  it("telefon/e-posta/IBAN/plaka/tarih/adres maskelenir", () => {
    const r = maskEpikriz(
      "Tel 0532 123 45 67, ornek@kurum.com, IBAN TR33 0006 1005 1978 6457 8413 26, " +
        "plaka 34 ABC 123, 01.02.1980 tarihinde Bağdat Caddesi No:12'de oturuyor."
    );
    for (const label of ["[TELEFON]", "[EPOSTA]", "[IBAN]", "[PLAKA]", "[TARIH]", "[ADRES]"]) {
      expect(r.maskedText).toContain(label);
    }
    expect(r.maskedText).not.toContain("ornek@kurum.com");
    expect(r.maskedText).not.toContain("34 ABC 123");
  });

  it("kurum adını maskeler", () => {
    const r = maskEpikriz("İstanbul Devlet Hastanesi'ne sevk edildi.");
    expect(r.maskedText).toContain("[KURUM]");
    expect(r.maskedText).not.toContain("Hastanesi");
  });

  it("PII içermeyen tıbbi metni değiştirmez", () => {
    const text = "Toraks BT'de sağ alt lobda 8 mm boyutlu nodül saptandı. Hemodinamik stabil.";
    expect(maskEpikriz(text).maskedText).toBe(text);
  });
});

describe("cleanHea", () => {
  const hea = [
    "REC001 12 250 2500",
    "#Age: 67",
    "#Sex: M",
    "#Dx: 426783006,164890007",
    "#Rx: 5 mg metoprolol",
    "#Hx: Hasta AHMET YILMAZ, T.C. 10000000146",
    "#PatientName: John Doe",
    "# signal comment",
  ].join("\n");

  it("kayıt adını pseudonymleştirir, yaşı bantlar, cinsiyeti siler", async () => {
    const { text, report } = await cleanHea(hea, SALT);
    expect(report.recordPseudonym).toMatch(/^[0-9a-f]{16}$/);
    expect(text).not.toContain("REC001");
    expect(report.ageBanded).toBe("67 -> 60-69");
    expect(text).toContain("#Age: 60-69");
    expect(report.sexRemoved).toBe(true);
    expect(text).not.toContain("#Sex: M");
  });

  it("Dx'i korur, Rx'i tutar, Hx'teki PII'ı maskeler, bilinen PHI alanını siler", async () => {
    const { text, report } = await cleanHea(hea, SALT);
    // Dx korunur (klinik sınıflandırma sinyali).
    expect(text).toContain("#Dx: 426783006,164890007");
    // Rx serbest metindir ama PII taşımaz → olduğu gibi kalır.
    expect(text).toContain("#Rx: 5 mg metoprolol");
    // Hx PII taşır → maskelenir.
    expect(text).not.toContain("AHMET YILMAZ");
    expect(text).toContain("[TC_KIMLIK]");
    expect(report.maskedFields.some((f) => f.startsWith("Hx ("))).toBe(true);
    // Tanınan PHI alan adı tamamen kaldırılır.
    expect(text).not.toContain("John Doe");
    expect(report.maskedFields).toContain("PatientName (kaldirildi)");
  });

  it("PII içermeyen sinyal yorumunu korur", async () => {
    const { text } = await cleanHea(hea, SALT);
    expect(text).toContain("# signal comment");
  });
});

describe("cleanDicom", () => {
  it("Explicit VR LE: PHI'yi temizler, özel etiketleri siler, pikseli korur", async () => {
    const original = buildExplicitDicom();
    const { bytes, report } = await cleanDicom(original, SALT);

    expect(report.removed).toContain("0008,0080"); // InstitutionName
    expect(report.removed).toContain("0010,0040"); // PatientSex
    expect(report.hashed).toContain("0010,0010"); // PatientName
    expect(report.hashed).toContain("0010,0020"); // PatientID
    expect(report.privateTagsRemoved).toBe(1);

    const text = new TextDecoder("latin1").decode(bytes);
    expect(text).not.toContain("Hospital X");
    expect(text).not.toContain("DOE^JOHN");
    expect(text).not.toContain("PID-42");
    expect(text).not.toContain("PRIVATE");

    // 3 remove edilen eleman (18+10+16 bayt); hash'ler uzunluğu korur.
    expect(bytes.length).toBe(original.length - 44);
    // Piksel verisi korunmuş olmalı.
    expect(Array.from(bytes.slice(-4))).toEqual([1, 2, 3, 4]);
  });

  it("Implicit VR LE: ayrıştırıcı kaymadan temizlik yapar", async () => {
    const original = buildImplicitDicom();
    const { bytes, report } = await cleanDicom(original, SALT);

    expect(report.removed).toContain("0008,0080");
    expect(report.removed).toContain("0010,0040");
    expect(report.hashed).toContain("0010,0010");

    const text = new TextDecoder("latin1").decode(bytes);
    expect(text).not.toContain("Hospital X");
    expect(text).not.toContain("DOE^JOHN");
    expect(Array.from(bytes.slice(-4))).toEqual([9, 8, 7, 6]);
  });

  it("DICM öneki yoksa hata fırlatır", async () => {
    await expect(cleanDicom(new Uint8Array(200), SALT)).rejects.toThrow("DICM");
  });
});

describe("getOrCreateAnonSalt / hashAnonId", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("tuz tarayıcıda üretilir, tekrar kullanılır ve saklanır", () => {
    const s1 = getOrCreateAnonSalt();
    const s2 = getOrCreateAnonSalt();
    expect(s1).toMatch(/^[0-9a-f]{64}$/);
    expect(s2).toBe(s1);
    expect(window.localStorage.getItem("pulsar_anon_salt")).toBe(s1);
  });

  it("hashAnonId deterministiktir ve tuza duyarlıdır", async () => {
    const a = await hashAnonId("10000000146", "salt-a");
    const b = await hashAnonId("10000000146", "salt-a");
    const c = await hashAnonId("10000000146", "salt-b");
    expect(a).toMatch(/^[0-9a-f]{32}$/);
    expect(b).toBe(a);
    expect(c).not.toBe(a);
  });
});
