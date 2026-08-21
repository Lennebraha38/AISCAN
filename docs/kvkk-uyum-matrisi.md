# KVKK Uyum Matrisi — Pulsar-KKDS

6698 sayılı Kişisel Verilerin Korunması Kanunu ve Kişisel Sağlık Verileri
Yönetmeliği (Kişisel Sağlık Verilerinin İşlenmesi ve Mahremiyetinin Korunması
Yönetmeliği) gereksinimlerinin teknik kontrollerle eşleştirilmesi.

| # | KVKK / Yönetmelik Gereksinimi | Pulsar-KKDS Teknik Kontrolü | Kod Referansı |
|---|---|---|---|
| 1 | **Veri minimizasyonu (md.4/2)** — işlenen veri amaç için yeterli, gerekli olmalı | DICOM PHI tag'leri ve epikriz PII'si sunucuya gitmeden önce istemcide temizlenir; backend `studies` tablosunda hiçbir kimlik kolonu yoktur | `anonymizer/dicom_cleaner`, `anonymizer/pii_nlp`, `frontend/lib/browser-anonymizer.ts` |
| 2 | **İşleme şeffaflığı (md.10-11)** — ilgili kişi bilgilendirilmeli | Yükleme ekranında "Temizlenen Alanlar" paneli canlı olarak hangi alanların kaldırıldı/değiştirildiğini gösterir | `frontend/app/studies/new/page.tsx` |
| 3 | **Teknik/idari tedbirler (md.12)** — güvenli veri işleme | Zero-Knowledge Architecture: ham veri ağa çıkmaz. Defans-in-depth: backend gelen metinde PII deseni görürse isteği 422 ile reddeder ve `PII_REJECTED` audit kaydı yazar | `backend/app/services/pii_guard.py`, `backend/app/api/v1/studies.py` |
| 4 | **İşlem güvenliği — yetkisiz erişim** | JWT access+refresh token, rol bazlı erişim (admin/hekim/radyolog/asistan), endpoint bazlı rol dependency'leri | `backend/app/core/security.py`, `backend/app/core/deps.py` |
| 5 | **İşlem güvenliği — silinemez kayıt/takip** | `audit_logs` tablosu append-only: Postgres trigger'ı UPDATE/DELETE'i engeller; ORM seviyesinde de event listener koruması vardır | `backend/app/models/__init__.py`, `alembic/versions/0001_initial.py` |
| 6 | **Sağlık verisi ayrıcalığı** — kişisel sağlık verisi ancak yasal dayanakla işlenir | Sistem yalnız anonim/pseudonym veri saklar (`anon_study_hash` = SHA256(salt+id)); gerçek kimlik yalnız hastane sisteminde kalır | `frontend/lib/browser-anonymizer.ts:hashAnonId` |
| 7 | **Veri güvenliği — şifreleme** | Şifreler PBKDF2-SHA256 (120k tur) ile hash'lenir; pseudonym SHA-256 salted; üretim dağıtımında TLS zorunludur (reverse proxy katmanı) | `backend/app/core/security.py` |
| 8 | **Aydınlatma yükümlülüğü** — açık rıza akışı | Platform hekim adına çalışır; hasta kimliği sisteme hiç girilmediği için hasta verisi işlenmez (veri minimizasyonunun uç hali) | Mimari genel |

## Veri Akışı (Zero-Knowledge)

```
[Hasta DICOM + Epikriz]
        │  (yalnız istemcide)
        ▼
[Browser Anonymizer] ──► Temizlenen Alanlar Raporu (UI'da gösterilir)
        │
        │  yalnız anonim çıktı ağdan geçer:
        ▼
[FastAPI Backend] ──► PostgreSQL (anon_study_hash, masked_epikriz)
        │                        ▲
        ▼                        │ pgvector benzer vaka
[AI Core: Vision+NLP+XAI] ───────┘
        │
        ▼
[Hekim Onayı (Human-in-the-Loop)] ──► review_decisions + audit_logs
```

## Doğrulama Testleri

- `anonymizer/tests/test_dicom_cleaner.py`: PHI tag taraması sıfır sızıntı
- `anonymizer/tests/test_pii_nlp.py`: 34 vaka, TC checksum dahil
- `backend/tests/test_api.py::test_pii_in_request_rejected_422`: defans-in-depth
