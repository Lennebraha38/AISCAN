/**
 * Tarayıcı tarafı anonimizasyon motoru (Modül 1 TS portu).
 *
 * Zero-Knowledge Architecture: bu dosyanın tüm işlevleri istemcide çalışır;
 * ham DICOM/epikriz verisi asla ağa çıkmaz. WASM paketi hazır olana dek
 * birincil yol budur (aynı sözleşme: anonymizer-client.ts).
 */

// ---------- Türkçe PII maskeleme ----------

export interface PiiFinding {
  type: string;
  start: number;
  end: number;
  label: string;
}

export interface MaskResult {
  maskedText: string;
  findings: PiiFinding[];
}

const LABELS: Record<string, string> = {
  TC_KIMLIK: "[TC_KIMLIK]",
  TELEFON: "[TELEFON]",
  EPOSTA: "[EPOSTA]",
  IBAN: "[IBAN]",
  PASAPORT: "[PASAPORT]",
  PLAKA: "[PLAKA]",
  TARIH: "[TARIH]",
  ADRES: "[ADRES]",
  KISI_ADI: "[KISI_ADI]",
  KURUM: "[KURUM]",
};

export function tcKimlikGecerli(num: string): boolean {
  if (!/^[1-9][0-9]{10}$/.test(num)) return false;
  const d = num.split("").map(Number);
  const odd = d[0] + d[2] + d[4] + d[6] + d[8];
  const even = d[1] + d[3] + d[5] + d[7];
  if ((odd * 7 - even) % 10 !== d[9]) return false;
  return d.slice(0, 10).reduce((a, b) => a + b, 0) % 10 === d[10];
}

const PATTERNS: { type: string; re: RegExp }[] = [
  { type: "TC_KIMLIK", re: /\b[1-9]\d{10}\b/g },
  { type: "TELEFON", re: /(?:\+90|0090|0)?[\s.(]*5\d{2}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}\b/g },
  { type: "EPOSTA", re: /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g },
  { type: "IBAN", re: /\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b/g },
  { type: "PASAPORT", re: /\b(?:U\+[A-Z]\d{7}|[A-Z]{1,2}\d{7,8})\b/g },
  // Türk plaka: "34 ABC 123", "06 BKM 412", "35 A 1234"
  { type: "PLAKA", re: /\b\d{2}\s?(?:[A-Z]|[A-Z]{2,3})\s?\d{2,4}\b/g },
  // Bağlam duyarlı doğum tarihi: "doğum tarihi 01.01.1980", "D.T.: 01/01/1980"
  {
    type: "TARIH",
    re: /(?:d(?:o|ö)[gğ](?:u|ü)m\s*t(?:a)r[ii]h[iı]|d\.?t\.?)\s*[:=]?\s*(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{8})/gi,
  },
  // Genel tarih (dd.mm.yyyy) — quasi-identifier
  { type: "TARIH", re: /\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b/g },
  // Adres: mahalle/cadde/sokak kalıpları
  {
    type: "ADRES",
    re: /\b[A-ZÇĞİÖŞÜ][\wçğıöşü]*(?:\s+[A-ZÇĞİÖŞÜ]?[\wçğıöşü.]*)*\s+(?:Mah(?:allesi)?\.?|Cad(?:desi)?\.?|Sok(?:ağı)?\.?)(?:\s*,?\s*(?:No\s*:?\s*\d+[/\w]*|Kat\s*:?\s*\d+|Daire\s*:?\s*\d+))*/g,
  },
];

const UNVANLU_AD =
  /((?:Prof\.?\s*Dr\.?|Do[cç]\.\s*Dr\.?|Op\.\s*Dr\.?|Uz(?:m)?\.\s*Dr\.?|Dr\.?|[Dd]oktor|Hasta|Sn\.?)\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+){1,2})/g;
const BUYUK_AD = /\b([A-ZÇĞİÖŞÜ]{2,}(?:\s+[A-ZÇĞİÖŞÜ]{2,}){1,2})\b/g;
const KURUM_RE =
  /\b[A-ZÇĞİÖŞÜ][\wçğıöşüÇĞİÖŞÜ.]*(?:\s+(?:ve|ile|[A-ZÇĞİÖŞÜ][\wçğıöşü]*))*\s+(?:Devlet\s+)?(?:Hastanesi|Hastane[sıi]|Medikal\s*Merkez|Tıp\s*Merkezi|Poliklini[iğ]|Göz\s*Hastalıkları\s*Merkezi)\b|\b[A-ZÇĞİÖŞÜ][\wçğıöşü]*\s+Üniversitesi\s+Tıp\s+Fakültesi(?:\s+Hastanesi)?\b/g;

export function maskEpikriz(text: string): MaskResult {
  const raw: { start: number; end: number; type: string }[] = [];
  const push = (type: string, start: number, end: number) => raw.push({ start, end, type });

  for (const { type, re } of PATTERNS) {
    for (const m of text.matchAll(re)) {
      if (type === "TC_KIMLIK" && !tcKimlikGecerli(m[0])) continue;
      push(type, m.index!, m.index! + m[0].length);
    }
  }
  for (const m of text.matchAll(UNVANLU_AD)) push("KISI_ADI", m.index!, m.index! + m[0].length);
  for (const m of text.matchAll(KURUM_RE)) push("KURUM", m.index!, m.index! + m[0].length);
  for (const m of text.matchAll(BUYUK_AD)) {
    if (!raw.some((r) => m.index! >= r.start && m.index! < r.end)) {
      push("KISI_ADI", m.index!, m.index! + m[0].length);
    }
  }

  raw.sort((a, b) => a.start - b.start || b.end - a.end);
  const picked: typeof raw = [];
  let lastEnd = -1;
  for (const r of raw) {
    if (r.start >= lastEnd) {
      picked.push(r);
      lastEnd = r.end;
    }
  }

  let out = text;
  for (let i = picked.length - 1; i >= 0; i--) {
    const r = picked[i];
    out = out.slice(0, r.start) + LABELS[r.type] + out.slice(r.end);
  }
  return {
    maskedText: out,
    findings: picked.map((r) => ({ ...r, label: LABELS[r.type] })),
  };
}

// ---------- DICOM metadata temizleme ----------

/** (group,element) -> aksiyon. hash: pseudonym ile değiştir, remove: sil. */
const PHI_TAGS = new Map<string, "hash" | "remove">([
  ["0008,0050", "hash"], // AccessionNumber
  ["0008,0080", "remove"], // InstitutionName
  ["0008,0081", "remove"], // InstitutionAddress
  ["0008,0090", "remove"], // ReferringPhysicianName
  ["0008,1010", "remove"], // StationName
  ["0008,1030", "remove"], // StudyDescription
  ["0008,103E", "remove"], // SeriesDescription
  ["0008,1048", "remove"], // PhysiciansOfRecord
  ["0008,1050", "remove"], // PerformingPhysicianName
  ["0008,1060", "remove"], // NameOfPhysiciansReadingStudy
  ["0008,1070", "remove"], // OperatorsName
  ["0010,0010", "hash"], // PatientName
  ["0010,0020", "hash"], // PatientID
  ["0010,0030", "remove"], // PatientBirthDate
  ["0010,0032", "remove"], // PatientBirthTime
  ["0010,0040", "remove"], // PatientSex
  ["0010,1000", "remove"], // OtherPatientIDs
  ["0010,1001", "remove"], // OtherPatientNames
  ["0010,1010", "remove"], // PatientAge
  ["0010,1040", "remove"], // PatientAddress
  ["0010,1060", "remove"], // PatientMotherBirthName
  ["0020,0010", "hash"], // StudyID
  ["0020,4000", "remove"], // ImageComments
]);

export interface DicomCleanReport {
  removed: string[];
  hashed: string[];
  privateTagsRemoved: number;
}

async function sha256Hex(input: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function hashAnonId(value: string, salt: string): Promise<string> {
  return (await sha256Hex(salt + value)).slice(0, 32);
}

const ANON_SALT_KEY = "pulsar_anon_salt";

/**
 * Anonimleştirme tuzu.
 *
 * Koda GÖMÜLÜ sabit bir tuz (ör. "pulsar-kkds-salt") pakete girer ve
 * saldırganın TC kimlik gibi düşük entropili değerler için önceden hash
 * tablosu üretmesini (re-identification) mümkün kılar. Bunun yerine tuz
 * tarayıcıda rastgele üretilip saklanır; paketten okunamaz.
 */
export function getOrCreateAnonSalt(): string {
  if (typeof window === "undefined") {
    throw new Error("Anonimleştirme tuzu yalnızca tarayıcıda üretilebilir");
  }
  let salt = window.localStorage.getItem(ANON_SALT_KEY);
  if (!salt) {
    const rand = new Uint8Array(32);
    crypto.getRandomValues(rand);
    salt = Array.from(rand)
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
    window.localStorage.setItem(ANON_SALT_KEY, salt);
  }
  return salt;
}

interface Element {
  tag: string; // "GGGG,EEEE"
  start: number; // bayt aralığı (başlık dahil)
  end: number;
  vr: string | null;
  valueStart: number;
  valueEnd: number;
}

function elementHeader(
  buf: DataView,
  pos: number,
  isExplicit: boolean,
  u16: (o: number) => number,
  u32: (o: number) => number
): { vr: string | null; len: number; headerLen: number } {
  let vr: string | null = null;
  let len = 0;
  let headerLen = 8;
  if (isExplicit) {
    vr = String.fromCharCode(u16(pos + 4) & 0xff, (u16(pos + 4) >> 8) & 0xff);
    if (["OB", "OD", "OF", "OL", "OV", "OW", "SQ", "UC", "UR", "UT", "UN"].includes(vr)) {
      len = u32(pos + 8);
      headerLen = 12;
    } else {
      len = u16(pos + 6);
    }
  } else {
    len = u32(pos + 4);
  }
  return { vr, len, headerLen };
}

/**
 * Tanımsız uzunluklu (0xFFFFFFFF) bir değerin sonunu bulur: item
 * (FFFE,E000) ve sequence sınırlayıcılarını iç içe sayarak eşleşen
 * Sequence/Item Delimitation Item'dan SONRAKİ konumu döndürür. Böylece
 * ilk sequence'te DURMAK yerine üst düzeydeki tüm PHI etiketleri taranır.
 */
function skipUndefinedValue(
  buf: DataView,
  pos: number,
  isExplicit: boolean,
  u16: (o: number) => number,
  u32: (o: number) => number
): number {
  let depth = 0;
  while (pos + 8 <= buf.byteLength) {
    const group = u16(pos);
    const elem = u16(pos + 2);
    if (group === 0xfffe) {
      const len = u32(pos + 4);
      if ((elem === 0xe00d || elem === 0xe0dd) && len === 0) {
        if (depth === 0) return pos + 8; // kapsayıcıyı kapatan sınırlayıcı
        depth--;
        pos += 8;
        continue;
      }
      if (elem === 0xe000 && len === 0xffffffff) {
        depth++;
        pos += 8;
        continue;
      }
      if (elem === 0xe000) {
        pos += 8 + len;
        continue;
      }
      pos += 8;
      continue;
    }
    const hdr = elementHeader(buf, pos, isExplicit, u16, u32);
    const valueStart = pos + hdr.headerLen;
    if (hdr.len === 0xffffffff) {
      depth++;
      pos = valueStart;
      continue;
    }
    pos = valueStart + hdr.len;
  }
  return buf.byteLength;
}

function readElements(
  buf: DataView,
  isExplicit: boolean,
  little: boolean,
  startAt: number = 132 // 128 bayt preamble + "DICM" (ilk veri elemanı 132'de başlar)
): Element[] {
  const elements: Element[] = [];
  let pos = startAt;
  // DataView.getUint16/32 varsayılanı BIG-endian'dir; DICOM'de ise byte order
  // transfer syntax'ına bağlıdır. `little` burada aktarılmalı (aksi halde
  // little-endian dosyalarda tüm etiketler yanlış okunur ve PHI temizlenmez).
  const u16 = (o: number) => buf.getUint16(o, little);
  const u32 = (o: number) => buf.getUint32(o, little);

  while (pos + 8 <= buf.byteLength) {
    const group = u16(pos);
    const elem = u16(pos + 2);
    const tag = `${group.toString(16).padStart(4, "0")},${elem.toString(16).padStart(4, "0")}`;
    const { vr, len, headerLen } = elementHeader(buf, pos, isExplicit, u16, u32);

    const start = pos;
    const valueStart = pos + headerLen;
    let valueEnd: number;
    if (len === 0xffffffff) {
      // Tanımsız uzunluk (SQ/UN): sınırlayıcıya kadar tara ve İLERLE.
      valueEnd = skipUndefinedValue(buf, valueStart, isExplicit, u16, u32);
    } else {
      valueEnd = Math.min(valueStart + len, buf.byteLength);
    }
    elements.push({ tag, start, end: valueEnd, vr, valueStart, valueEnd });
    if (valueEnd <= start) break; // ilerleme yoksa sonsuz döngüyü önle
    pos = valueEnd;
  }
  return elements;
}

export async function cleanDicom(
  bytes: Uint8Array,
  salt: string
): Promise<{ bytes: Uint8Array; report: DicomCleanReport }> {
  const copy = new Uint8Array(bytes);
  const view = new DataView(copy.buffer);

  // Transfer syntax tespiti (FileMetaInformationGroupLength sonrası kabaca)
  const magic = String.fromCharCode(...copy.slice(128, 132));
  if (magic !== "DICM") throw new Error("Geçersiz DICOM: DICM öneki yok");

  // Meta grup her zaman Explicit VR LE'dir; dataset için meta içindeki
  // (0002,0010) TransferSyntaxUID okunur.
  // Meta grubu, dosyanın başındaki ARDIŞIK 0002 elemanlarıdır. Yalnızca bu
  // bloğu almak; implicit VR dataset'in (yanlışlıkla) explicit olarak
  // ayrıştırılması sonucu oluşabilecek sahte 0002 etiketlerinin datasetStart'ı
  // bozmasını önler.
  const metaElems: Element[] = [];
  for (const e of readElements(view, true, true)) {
    if (!e.tag.startsWith("0002,")) break;
    metaElems.push(e);
  }
  let tsuid = "1.2.840.10008.1.2"; // varsayım: implicit VR LE
  for (const e of metaElems) {
    if (e.tag === "0002,0010") {
      tsuid = new TextDecoder()
        .decode(copy.slice(e.valueStart, e.valueEnd))
        .replace(/\0+$/, "") // UI değeri tek bayt NULL ile doldurulur; trim bunu almaz
        .trim();
    }
  }
  // Yalnız "Implicit VR Little Endian" implicit'tir; diğer tüm transfer
  // syntax'ları (Explicit VR LE/BE, sıkıştırılmış, deflate) explicit VR
  // kullanır. Önceki `tsuid.includes("30e")` kontrolü her zaman false
  // dönüyordu ve explicit dosyalarda ayrıştırıcı baştan kayıyordu.
  const isExplicit = tsuid !== "1.2.840.10008.1.2";
  const little = tsuid !== "1.2.840.10008.1.2.2"; // Explicit VR Big Endian

  const report: DicomCleanReport = { removed: [], hashed: [], privateTagsRemoved: 0 };
  const edits: { start: number; end: number; replacement: Uint8Array }[] = [];
  const datasetStart = (() => {
    // meta grubunun bittiği yer: en büyük 0002 eleman sonu
    return metaElems.length ? Math.max(...metaElems.map((e) => e.end)) : 132;
  })();

  // Meta grubu her zaman Explicit VR LE'dir; bu yüzden dataset okuması
  // meta grubundan SONRA başlar. Aksi halde Implicit VR LE dosyalarda ayrıştırıcı
  // meta elemanlarını implicit uzunluk olarak okuyup kayıyor.
  const elems = readElements(view, isExplicit, little, datasetStart);
  for (const el of elems) {
    const [g, _e] = el.tag.split(",");
    const group = parseInt(g, 16);
    if (group % 2 === 1 && group > 0x0008) {
      // private tag -> tamamen çıkar
      edits.push({ start: el.start, end: el.end, replacement: new Uint8Array(0) });
      report.privateTagsRemoved++;
      continue;
    }
    const action = PHI_TAGS.get(el.tag);
    if (!action) continue;
    const length = el.valueEnd - el.valueStart;
    if (length <= 0) continue;

    if (action === "remove") {
      edits.push({ start: el.start, end: el.end, replacement: new Uint8Array(0) });
      report.removed.push(el.tag);
    } else {
      const original = new TextDecoder("latin1").decode(copy.slice(el.valueStart, el.valueEnd)).replace(/\0+$/, "");
      const pseudo = await sha256Hex(salt + original);
      const padded = pseudo.slice(0, Math.min(16, length)).padEnd(length, "\0");
      edits.push({
        start: el.valueStart,
        end: el.valueEnd,
        replacement: new TextEncoder().encode(padded),
      });
      report.hashed.push(el.tag);
    }
  }

  // Tersten uygula (uzunluk değişimlerinde kaymayı önler)
  edits.sort((a, b) => b.start - a.start);
  const chunks: Uint8Array[] = [];
  let cursor = copy.length;
  for (const ed of edits) {
    if (ed.end > cursor) continue;
    chunks.unshift(copy.subarray(ed.end, cursor));
    cursor = ed.start;
    if (ed.replacement.length) chunks.unshift(ed.replacement);
  }
  chunks.unshift(copy.subarray(0, cursor));

  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) {
    out.set(c, off);
    off += c.length;
  }
  return { bytes: out, report };
}

// ---------------------------------------------------------------------------
// WFDB .hea (EKG basligi) anonimlestirme — Python ecg_deid TS portu
// ---------------------------------------------------------------------------

export interface HeaCleanReport {
  recordPseudonym: string | null;
  ageBanded: string | null;
  sexRemoved: boolean;
  maskedFields: string[];
}

function ageBand(age: number): string {
  const lo = Math.floor(age / 10) * 10;
  return `${lo}-${lo + 9}`;
}

/** WFDB .hea metnini istemcide KVKK uyumlu hale getirir. */
export async function cleanHea(content: string, salt: string): Promise<{ text: string; report: HeaCleanReport }> {
  const lines = content.split(/\r?\n/);
  const report: HeaCleanReport = {
    recordPseudonym: null,
    ageBanded: null,
    sexRemoved: false,
    maskedFields: [],
  };
  let pseudo: string | null = null;
  const pseudonyms = new Map<string, string>();
  const out: string[] = [];

  // Bilinen PHI alan adları (küçük harf) — değeri doğrudan kimlik taşır.
  const PHI_FIELD_NAMES = new Set([
    "patientname", "patient", "patientid", "name", "id", "dob", "birthdate",
    "birth", "birthday", "birthname", "comments", "comment", "address",
    "hospital", "institution", "institutionname", "physician", "doctor",
    "mrn", "lastname", "firstname", "surname", "ssn", "accession",
    "accessionnumber", "phone", "telephone", "email", "tc", "tcno", "gender",
  ]);
  const PHI_FIELD_HINTS = [
    "patient", "physician", "doctor", "mrn", "dob", "birthdate", "birth",
    "ssn", "accession", "address", "institution", "hospital",
  ];
  const isPhiField = (n: string): boolean => {
    const l = n.toLowerCase();
    return PHI_FIELD_NAMES.has(l) || PHI_FIELD_HINTS.some((h) => l.includes(h));
  };

  for (const line of lines) {
    if (!line.startsWith("#")) {
      // teknik satir: kayit adi / .mat referansi pseudonymize edilir.
      // Alan adi eslesmesi buyuk/kucuk harf duyarsiz ve genisletilmistir.
      const first = line.trim().split(/\s+/)[0] ?? "";
      const m = first.match(/^([A-Za-z0-9][A-Za-z0-9_-]*?)(\.mat)?$/);
      if (m) {
        const recId = m[1];
        let ps = pseudonyms.get(recId);
        if (!ps) {
          ps = (await sha256Hex(salt + recId)).slice(0, 16);
          pseudonyms.set(recId, ps);
          if (!pseudo) {
            pseudo = ps;
            report.recordPseudonym = ps;
          }
        }
        out.push(line.replace(recId, ps));
      } else {
        out.push(line);
      }
      continue;
    }

    const fm = line.match(/^#\s*(Age|Sex|Dx|Rx|Hx|Sx)\s*:\s*(.*)$/i);
    if (fm) {
      const name = fm[1];
      const key = name.toLowerCase();
      const value = fm[2].trim();
      if (key === "age") {
        const age = parseInt(value, 10);
        if (!Number.isNaN(age)) {
          report.ageBanded = `${value} -> ${ageBand(age)}`;
          out.push(`#${name}: ${ageBand(age)}`);
        } else {
          out.push("");
        }
      } else if (key === "sex") {
        report.sexRemoved = true;
        out.push("");
      } else if (key === "rx" || key === "hx" || key === "sx") {
        // serbest metin: temel maskeleme uygula
        const res = maskEpikriz(value);
        if (res.findings.length) {
          report.maskedFields.push(`${name} (${res.findings.length} PII)`);
          out.push(`#${name}: ${res.maskedText}`);
        } else {
          out.push(line);
        }
      } else {
        out.push(line); // Dx korunur
      }
      continue;
    }

    // Taninmayan "# Alan: deger" satirlari: PHI ise kaldir, degilse maskele.
    const am = line.match(/^#\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.*)$/);
    if (am) {
      const name = am[1];
      const value = am[2].trim();
      if (isPhiField(name)) {
        report.maskedFields.push(`${name} (kaldirildi)`);
        continue;
      }
      const res = maskEpikriz(value);
      if (res.findings.length) {
        report.maskedFields.push(`${name} (${res.findings.length} PII)`);
        out.push(`#${name}: ${res.maskedText}`);
      } else {
        out.push(line);
      }
      continue;
    }

    // Serbest "#" yorum satiri: PII tasiyorsa maskele, yoksa koru.
    const cres = maskEpikriz(line);
    if (cres.findings.length) {
      report.maskedFields.push(`# yorum (${cres.findings.length} PII)`);
      out.push(cres.maskedText);
    } else {
      out.push(line);
    }
  }
  return { text: out.join("\n") + "\n", report };
}
