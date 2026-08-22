# Pulsar-KKDS

**KVKK Uyumlu Multimodal Tıbbi Karar Destek Platformu (SaMD)**

TEKNOFEST 2026 — Yapay Zekâ ile Sağlıkta Devrim Yarışması, **Lise /
Kardiyoloji** görevi: 12 derivasyonlu EKG sinyallerini üç üst sınıfa
(Aritmiler / İletim Bozuklukları / Normal) macro F1 ile sınıflandırır; Türkçe
epikriz analizi ve radyoloji görüntü akışı ikincil modality olarak aynı
platformda çalışır.

> ⚠️ Bu sistem bir **Karar Destek Sistemidir (SaMD)**. Nihai klinik karar hekim
> sorumluluğundadır (MDR human-in-the-loop).

## Üç Sütunlu Mimari

| Sütun | Uygulama |
|---|---|
| **KVKK** | Zero-Knowledge Architecture: DICOM PHI tag'leri, WFDB `.hea` kimlik alanları ve epikriz PII'si istemcide temizlenir; sunucuya yalnız anonim veri ulaşır (`.hea` dosyası hiç gönderilmez) |
| **MDR** | Human-in-the-loop: AI çıktısı hekim onayı olmadan kesinleşmez; append-only audit log |
| **XAI** | Grad-CAM 1D (zaman × karar odağı) + derivasyon saliency matrisi + token düzeyi metin attribution |

## EKG Hattı (ana görev)

- Veri: PhysioNet ECG Arrhythmia (WFDB) → SNOMED üst-sınıf haritası
  (`blok > aritmi > normal` önceliği) → stratified seçki ~16k kayıt
- Ön işleme: bazal salınım → 0.5–40 Hz → 50 Hz notch → z-skor → 10 sn @ 250 Hz
- Baseline: el yapımı ritim/morfoloji özellikleri + sklearn (referans)
- Model: **ECGResNet-1D** (~2.2M param, CPU'da eğitilebilir), class-weighted CE,
  macro F1 optimizasyonu, erken durdurma
- XAI: Grad-CAM 1D şeridi + derivasyon saliency; viewer'da dalga formu üzerine bindirilir

Eğitimi yeniden üretme:

```bash
cd ai-core
../.venv/bin/python -m app.ecg.data   scan --data-dir ../data/ecg   # .hea tarama
../.venv/bin/python -m app.ecg.data   select --data-dir ../data/ecg # stratified seçki
../.venv/bin/python -m app.ecg.data   fetch  --data-dir ../data/ecg # .mat indirme
../.venv/bin/python -m app.ecg.train build-cache --data-dir ../data/ecg
../.venv/bin/python -m app.ecg.train baseline    --data-dir ../data/ecg
../.venv/bin/python -m app.ecg.train deep        --data-dir ../data/ecg
../.venv/bin/python -m app.ecg.train robustness  --data-dir ../data/ecg
```

Sonuçlar ve grafikler: `docs/metrics/` · Model: `ai-core/models/`

## Hızlı Başlangıç

```bash
docker compose up -d --build     # postgres(pgvector) + api + ai-core + web
# demo kullanıcıları:
PYTHONPATH=backend .venv/bin/python backend/scripts/seed.py
```

- Web: http://localhost:3000 (`hekim@pulsar.demo / hekim-demo-1234`)
- API: http://localhost:8000/docs
- AI Core: http://localhost:8001/docs

## Yerel Geliştirme (Docker'sız)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e backend -e ai-core -e anonymizer/dicom_cleaner -e anonymizer/pii_nlp

# backend
DATABASE_URL=sqlite:///./pulsar-dev.db PYTHONPATH=backend uvicorn app.main:app --port 8000

# ai-core (ayrı terminal)
PYTHONPATH=ai-core uvicorn app.main:app --port 8001

# frontend (ayrı terminal)
cd frontend && npm install && npm run dev
```

## Testler

```bash
source .venv/bin/activate
PYTHONPATH=anonymizer/dicom_cleaner pytest anonymizer/tests/test_dicom_cleaner.py
PYTHONPATH=anonymizer/pii_nlp      pytest anonymizer/tests/test_pii_nlp.py
PYTHONPATH=ai-core                 pytest ai-core/tests
PYTHONPATH=backend                 pytest backend/tests
cd frontend && npm run build       # tip kontrolü dahil
```

## Depo Yapısı

```
├── TASK.md          # ajan görev planı
├── docs/            # şartname uyum matrisi, KVKK/MDR beyanları, demo senaryosu, metrics/
├── anonymizer/      # Modül 1: istemci/sunucu anonimizasyon (DICOM + WFDB .hea + Türkçe NLP)
├── ai-core/         # Modül 2: EKG (ECGResNet-1D, Grad-CAM 1D) + vision XAI + epikriz analizi
├── backend/         # Modül 3: FastAPI, PostgreSQL/pgvector, JWT, hekim onay logu
├── frontend/        # Modül 4: Next.js, 12-derivasyon EKG viewer, anonimleştirme paneli
└── data/ecg/        # PhysioNet indirme/manifest (git dışı; yeniden üretilebilir)
```

## Güvenlik Notları

- Gerçek secret'lar commit edilmez; `.env.example` şablondur.
- `audit_logs` tablosu append-only'dir (DB trigger + ORM koruması).
- Backend, maskelenmemiş PII içeren istekleri 422 ile reddeder (defans-in-depth).
