# Pulsar-KKDS

**SaMD Hedefli Multimodal Karar Destek Prototipi** (KVKK ilkeleri gözetilerek
tasarlanmıştır)

TEKNOFEST 2026 — Yapay Zekâ ile Sağlıkta Devrim Yarışması, **Lise /
Kardiyoloji** görevi: 12 derivasyonlu EKG sinyallerini üç üst sınıfa
(Aritmiler / İletim Bozuklukları / Normal) macro F1 ile sınıflandırır; Türkçe
epikriz analizi ve radyoloji görüntü akışı ikincil modality olarak aynı
platformda çalışır.

> ⚠️ **Dürüst konumlandırma:** Bu bir **karar destek prototipidir**; onaylanmış
> bir tıbbi cihaz (SaMD) veya klinik üretim sistemi **değildir**. Nihai klinik
> karar hekim sorumluluğundadır (MDR human-in-the-loop). Görüntü (radyoloji) ve
> NLP modülleri **demo heuristiğidir** (eğitilmiş klinik model değildir). Klinik
> kanıt ve anonimleştirme kapsamı sınırları için bkz.
> **[docs/SINIRLAMALAR.md](docs/SINIRLAMALAR.md)**.

## Üç Sütunlu Mimari

| Sütun | Uygulama |
|---|---|
| **Gizlilik (KVKK ilkeleri)** | Zero-Knowledge tasarım: DICOM PHI tag'leri (iç içe sequence'ler dahil), PNG/JPEG meta verisi (EXIF/XMP/ICC/text), WFDB `.hea` kimlik alanları ve epikriz PII'si istemcide temizlenir; sunucuya yalnız anonim veri ulaşır (`.hea` dosyası hiç gönderilmez). Kapsam sınırları için bkz. docs/SINIRLAMALAR.md |
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
../.venv/bin/python -m app.ecg.train stage2      --data-dir ../data/ecg # 2. aşama (fine-grained)
```

**Config dosyası ile eğitim (yeni):**

```bash
cd ai-core
../.venv/bin/python -m app.ecg.train deep --config config.yaml --data-dir ../data/ecg
../.venv/bin/python -m app.ecg.train stage2 --config config.yaml --data-dir ../data/ecg
```

Sonuçlar ve grafikler: `docs/metrics/` · Model: `ai-core/models/`

> CI (GitHub Actions): `.github/workflows/train.yml` veri indirme → cache → eğitim →
> robustness → stage2 sürecini otomatik çalıştırır. Model + metrik + figürler
> **artifact olarak yüklenir** (doğrudan `main`'e commit edilmez; sürümleme ve
> inceleme release/PR süreciyle yapılır).

## Hızlı Başlangıç

```bash
# Üretim benzeri çalıştırma için güçlü secret'lar ZORUNLUDUR
# (docker-compose PULSAR_ENV=production ile başlar; zayıf varsayılan reddedilir).
cp .env.example .env
python - <<'PY'
import secrets, pathlib
p = pathlib.Path(".env"); t = p.read_text(encoding="utf-8")
t = t.replace("JWT_SECRET=replace-with-a-long-random-secret", f"JWT_SECRET={secrets.token_hex(32)}")
t = t.replace("ANON_SALT=replace-with-a-random-anon-salt", f"ANON_SALT={secrets.token_hex(16)}")
p.write_text(t, encoding="utf-8")
PY

docker compose up -d --build     # postgres(pgvector) + api + ai-core + web
# demo kullanıcıları:
PYTHONPATH=backend .venv/bin/python backend/scripts/seed.py
```

- Web: http://localhost:3000 (`hekim@pulsar.demo / hekim-demo-1234`)
- API: http://localhost:8000/docs
- AI Core: http://localhost:8001/docs

> Güvenlik notu: `JWT_SECRET` (≥32 karakter) ve `ANON_SALT` (≥16 karakter)
> üretimde zorunludur. `PULSAR_ENV=production` iken bu değerler eksik/zayıfsa
> uygulama başlamaz. Ters proxy (Vercel/nginx) arkasında `TRUST_FORWARDED_FOR=1`
> verin; aksi halde audit IP'si için `X-Forwarded-For` güvenilmez.

## Yerel Geliştirme (Docker'sız)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e backend -e ai-core -e anonymizer/dicom_cleaner -e anonymizer/pii_nlp -e anonymizer/ecg_deid

# backend
DATABASE_URL=sqlite:///./pulsar-dev.db PYTHONPATH=backend uvicorn app.main:app --port 8000

# ai-core (ayrı terminal)
PYTHONPATH=ai-core uvicorn app.main:app --port 8001

# frontend (ayrı terminal)
cd frontend && npm install && npm run dev
```

## Model Export (ONNX / TorchScript)

Eğitilmiş modeli production için ONNX veya TorchScript formatına dönüştürme:

```bash
# Ek bağımlılıklar (ihracat için, çalışma zamanında gerekmez)
pip install onnx onnxruntime

# ONNX export (+ doğrulama)
python scripts/export_onnx.py \
    --model-path ai-core/models/ecg_resnet.pt \
    --output-path ai-core/models/ecg_resnet.onnx \
    --verify

# ONNX + TorchScript export
python scripts/export_onnx.py \
    --model-path ai-core/models/ecg_resnet.pt \
    --output-path ai-core/models/ecg_resnet.onnx \
    --torchscript-path ai-core/models/ecg_resnet.ts \
    --verify

# Dinamik batch ekseni olmadan (sabit batch) export
python scripts/export_onnx.py --no-dynamic
```

- ONNX modeli `onnxruntime` ile CPU/GPU'da hızlı inference için kullanılabilir.
- `--verify` PyTorch ve ONNX/TorchScript çıktılarını karşılaştırır (maks. fark ~1e-6).
- TorchScript ihracatı, Grad-CAM hook'larını geçici olarak kaldırır (tracing
  kısıtı) ve işlem sonunda geri takar.

## Metrik Görselleri

Commit edilmiş metrik dosyalarından (`docs/metrics/*.json`) tekrar üretilebilir
karışıklık matrisi ve öğrenme eğrisi grafikleri:

```bash
python scripts/plot_metrics.py
# -> docs/figures/confusion_matrix.png, learning_curves.png, baseline_confusion_matrix.png
```

## Demo Verileri (sentetik)

Repo'da 3 adet **sentetik** demo EKG kaydı bulunur (`data/ecg/demo/`):
`SX00001` (normal), `SX00002` (AFib), `SX00003` (LBBB). Bu kayıtlar
`scripts/gen_demo_ecg.py` ile üretilen matematiksel dalga formlarıdır; gerçek
hasta verisi değildir ve PhysioNet kayıtlarıyla karıştırılmamalıdır (her `.hea`
içinde `#Synthetic: true` işareti vardır). Yeniden üretmek için:

```bash
python scripts/gen_demo_ecg.py data/ecg/demo
```

## Testler

```bash
source .venv/bin/activate
PYTHONPATH=anonymizer/dicom_cleaner:anonymizer/pii_nlp:anonymizer/ecg_deid pytest anonymizer/tests
PYTHONPATH=ai-core                 pytest ai-core/tests
PYTHONPATH=backend                 pytest backend/tests
cd frontend && npm test            # vitest birim testleri (anonimleştirme)
cd frontend && npm run build       # tip kontrolü dahil
```

**Smoke testleri (hızlı doğrulama; ekstra PYTHONPATH gerekmez):**

```bash
# ai-core
cd ai-core && python -m pytest tests/test_smoke.py -v

# backend
cd backend && python -m pytest tests/test_smoke.py -v

# anonymizer (DICOM + PII + EKG .hea uçtan uca)
cd anonymizer && python -m pytest tests/test_smoke.py -v
```

### Uçtan uca (E2E) testler — Playwright

Tarayıcı akışı (`login → epikriz anonimleştirme → kaydet+analiz → hekim onayı`)
`frontend/e2e/flow.spec.ts` içinde tanımlıdır. CI'da `.github/workflows/e2e.yml`
iş akışı ai-core (8001) + backend (8000, sqlite) servislerini başlatır, demo
kullanıcıları seed eder, ön yüzü derleyip Playwright (Chromium) ile testi koşar.

```bash
# Servisler ayakta (ai-core:8001, backend:8000) ve ön yüz derlenmiş olmalı:
cd frontend
npx playwright install chromium      # ilk seferde tarayıcı indirir
PLAYWRIGHT_BASE_URL=http://localhost:3000 npm run test:e2e
```

Yerel hata ayıklama için sistem tarayıcısı kullanılabilir (indirme gerekmez):

```bash
cd frontend
PLAYWRIGHT_CHANNEL=msedge npm run test:e2e
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
- Oturum: access token kısa ömürlüdür; **refresh token tarayıcıda HttpOnly
  çerezde** tutulur ve her yenilemede döndürülür (rotation). Şifre değişiminde
  `token_version` artırılarak tüm eski oturumlar düşürülür.
- Güvenlik politikası ve bildirim akışı: `SECURITY.md`.

## Bilinen Sınırlar

Sistem bir **karar destek prototipidir**; klinik üretim için hazır değildir.
Klinik kanıt, modality olgunluğu (görüntü/NLP = demo heuristiği) ve
anonimleştirme kapsamı sınırları (burn-in pixel metni, iç içe/üretici-özel
DICOM yapıları vb.) için bkz. **[docs/SINIRLAMALAR.md](docs/SINIRLAMALAR.md)**.

## Lisans

MIT — bkz. [LICENSE](LICENSE). Yazılım "olduğu gibi" sunulur; klinik kullanım
için onaylanmış bir tıbbi cihaz değildir.
