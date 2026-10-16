# Katkı Rehberi — Pulsar-KKDS

Katkılarınız için teşekkürler. Bu proje TEKNOFEST 2026 için geliştirilen çok
modüllü bir karar destek prototipidir.

## Geliştirme ortamı

```bash
git clone https://github.com/Lennebraha38/AISCAN.git
cd AISCAN
cp .env.example .env            # yerel ayarlar
docker compose up --build       # postgres + ai-core + api + web
```

Yerel geliştirme için `PULSAR_ENV=development` iken zayıf varsayılan
secret'lar kabul edilir; bunlar **üretimde reddedilir**.

## Testler

Kökteki `.venv` (Python) ve `frontend/node_modules` (Node) kullanılır.

```bash
# Backend
cd backend && PYTHONPATH="$PWD" python -m pytest tests/ -q

# ai-core
cd ai-core && PYTHONPATH="$PWD" python -m pytest tests/ -q

# Anonymizer
cd anonymizer && PYTHONPATH="$PWD/pii_nlp:$PWD/dicom_cleaner:$PWD/ecg_deid" \
  python -m pytest tests/ -q

# Frontend birim testleri (vitest)
cd frontend && npm test

# Frontend üretim derlemesi (tip kontrolü dahil)
cd frontend && npm run build
```

Lint (CI ile aynı):

```bash
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
```

## Dallanma ve commit akışı

- `main` korumalıdır; doğrudan kırıcı değişiklik göndermeyin.
- Özellik/düzeltme için kısa ömürlü dal açın: `feat/...`, `fix/...`, `docs/...`.
- Commit mesajları Conventional Commits'e yakın olsun:
  `fix(auth): refresh token'ı HttpOnly çereze taşı`.
- PR açmadan önce tüm testlerin yeşil olduğundan emin olun.

## Kod standartları

- **Python:** PEP 8, tip ipuçları (`from __future__ import annotations`),
  bloklayan çağrılar için `run_in_threadpool`.
- **TypeScript/React:** Next.js App Router, `strict` TS; sunucu durumunu
  istemcide gereksiz tutmayın.
- **Gizlilik:** Hiçbir modüle ham PHI girmemeli. Yeni bir alan/görüntü formatı
  eklerken anonimleştirme kapsamını (incl. meta veri/EXIF, iç içe DICOM
  sequence) ve testlerini de ekleyin.

## Güvenlik ve gizlilik kuralları

- Gerçek hasta verisi, kimlik bilgisi veya sır **commit etmeyin**.
- `.env` değişkenlerini yalnızca `.env.example` üzerinden belgeleyin.
- Güvenlik açıkları için bkz. `SECURITY.md`.

## Pull request kontrol listesi

- [ ] Değişiklik tek bir konuya odaklı ve açıklaması net.
- [ ] İlgili testler eklendi/güncellendi ve yerel olarak yeşil.
- [ ] Dokümantasyon (README/docs) gerekiyorsa güncellendi.
- [ ] PHI/secret sızıntısı yok.
