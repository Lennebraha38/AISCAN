# Pulsar-KKDS

**KVKK Uyumlu Multimodal Tıbbi Karar Destek Platformu (SaMD)**

Akciğer X-Ray/CT taramaları ile Türkçe hasta epikriz raporlarını eş zamanlı
analiz ederek risk skorlaması ve anomali tespiti yapan SaaS klinik karar
destek sistemi.

> ⚠️ Bu sistem bir **Karar Destek Sistemidir (SaMD)**. Nihai klinik karar hekim
> sorumluluğundadır (MDR human-in-the-loop).

## Üç Sütunlu Mimari

| Sütun | Uygulama |
|---|---|
| **KVKK** | Zero-Knowledge Architecture: DICOM PHI tag'leri ve epikriz PII'si istemcide temizlenir; sunucuya yalnız anonim veri ulaşır |
| **MDR** | Human-in-the-loop: AI çıktısı hekim onayı olmadan kesinleşmez; append-only audit log |
| **XAI** | Grad-CAM/enerji saliency ısı haritaları + token düzeyi metin attribution |

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
├── TASK.md          # ajan görev planı (tüm görevler tamamlandı)
├── docs/            # KVKK uyum matrisi, MDR SaMD beyanı, jüri demo senaryosu
├── anonymizer/      # Modül 1: istemci tarafı anonimizasyon (DICOM + Türkçe NLP)
├── ai-core/         # Modül 2: vision + Grad-CAM XAI + Türkçe epikriz analizi
├── backend/         # Modül 3: FastAPI, PostgreSQL/pgvector, JWT, hekim onay logu
└── frontend/        # Modül 4: Next.js, Cornerstone viewer, anonimleştirme paneli
```

## Güvenlik Notları

- Gerçek secret'lar commit edilmez; `.env.example` şablondur.
- `audit_logs` tablosu append-only'dir (DB trigger + ORM koruması).
- Backend, maskelenmemiş PII içeren istekleri 422 ile reddeder (defans-in-depth).
