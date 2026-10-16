# Changelog

Bu proje [Semantic Versioning](https://semver.org/lang/tr/) ve
[Keep a Changelog](https://keepachangelog.com/tr/1.0.0/) biçimini izler.

## [Unreleased]

### Added
- Tarayıcı düzeyinde anonimleştirme testleri (vitest + jsdom) ve CI `frontend` işi.
- `run_stage2` (hiyerarşik başlık eğitimi) için duman testi.
- EKG değerlendirmesinde sınıf bazlı metrikler, Wilson %95 güven aralığı ve
  hata analizi; sabit/izlenebilir test seti bilgisi.
- Açık kaynak/kurumsal temel dosyaları: `LICENSE`, `SECURITY.md`,
  `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue/PR şablonları, `CHANGELOG.md`.
- `docs/SINIRLAMALAR.md` — bilinen sınırlar ve dürüst konumlandırma.

### Changed
- SaMD/KVKK iddiaları yumuşatıldı: "SaMD hedefli karar destek prototipi".
- Vision/NLP modülleri açıkça "demo heuristiği" olarak etiketlendi.
- Docker Compose servislerine `restart: unless-stopped` eklendi.

### Security
- Refresh token tarayıcıda `localStorage` yerine **HttpOnly çerezde** tutuluyor;
  her yenilemede rotasyon uygulanıyor.
- PNG/JPEG meta verisi (EXIF/XMP/ICC/text) istemcide temizleniyor.
- DICOM anonimleştirme iç içe (nested) sequence'lere özyinelemeli uygulanıyor.

### Fixed
- Tarayıcı DICOM ayrıştırıcısında endian, dataset ofseti ve padding hataları.
- `run_stage2` metrik hesaplamasında sınıf etiketi kaynaklı çökme.

## [0.2.0] - 2026

### Added
- Çok modüllü mimari: `anonymizer`, `ai-core`, `backend`, `frontend`.
- FastAPI backend: RBAC, JWT, IDOR kontrolü, append-only audit log,
  insan-döngüde onay akışı.
- EKG hattı: ECGResNet-1D, Grad-CAM 1D ve derivasyon saliency.
- Türkçe epikriz PII maskeleme ve DICOM/WFDB `.hea` temizleme.
- Docker Compose, Alembic göçleri ve GitHub Actions CI.

[Unreleased]: https://github.com/Lennebraha38/AISCAN/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Lennebraha38/AISCAN/releases/tag/v0.2.0
