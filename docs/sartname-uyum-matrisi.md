# Şartname Uyum Matrisi — Pulsar-KKDS / AISCAN

**Yarışma:** TEKNOFEST 2026 — Sağlıkta Yapay Zekâ Yarışması
**Kategori:** Lise — Kardiyoloji / EKG Ritim Analizi
**Şartname:** V1.1 (21.01.2026) + güncel V2.0 (Lise bölümleri aynıdır)
**Not:** Üniversite+ kategorisindeki genetik varyant problemi kapsam dışında; lise şartnamesi (Bölüm 3.1, 3.1.1, 3.1.2, 7.2, 7.7) tam kapsamda yürütülmüştür.

## Görev Tanımı ↔ Uygulama

| Şartname Maddesi (alıntı özeti) | Uygulama | Kanıt / Konum |
|---|---|---|
| **3.1** — 12 derivasyonlu EKG ile 3 üst sınıf: Ritim Bozuklukları / İletim Bozuklukları / Normal EKG; tek üst sınıf tahmini (multi-class) | SNOMED CT → üst sınıf haritası; çoklu etikette **blok > aritmi > normal** önceliği (gerçek veri dağılımıyla gerekçeli); model 3 çıkışlı, tek tahmin | `ai-core/app/ecg/labels.py`, `model.py` |
| **3.1.1** — Veri seti: PhysioNet **ECG Arrhythmia 1.0.0** (≈45 bin, 500 Hz, .mat/.hea, SNOMED-CT); ek açık/kendi verisi serbest | Birebir bu veri seti: 45.152 kayıt tarandı, 42.625 etiketli eşleşti, stratified seçki 15.983 (blok 2.983 / aritmi 6.500 / normal 6.500) | `data/ecg/selected.jsonl`, `data.py` |
| **3.1.2** — Birinci aşama metriği **macro F1**; karışıklık matrisi + öğrenme eğrisi + sınıf bazlı hata incelenecek | Tüm eğitim/doğrulama macro F1 ile yönetilir; testte karışıklık matrisi, öğrenme eğrileri ve sınıf bazlı rapor üretilir | `train.py`, `docs/figures/*.png`, `docs/metrics/deep_metrics.json` |
| **3.1.2** — İkinci aşama: ritim + iletişim altındaki **fine-grained** alt sınıflar (AFIB/AFL/AT/SVT/APB/VPB | LBBB/RBBB/AVB); kesin liste PSR sonrası | Donmuş backbone üzerinde superclass-bazlı alt kafalar; nadir alt gruplar 'other'da. `stage2` komutu + `docs/metrics/stage2_metrics.json` | `train.py stage2` |
| Ön işleme | Bazal salınım → 0.5–40 Hz Butterworth → 50 Hz notch → derivasyon bazlı z-skor → sabit 10 sn, eğitim/inference **250 Hz** (500 Hz veriden yeniden örnekleme; şartnameyi daraltmaz) | `ai-core/app/ecg/preprocess.py` |
| Sınıf dengesizliği | Stratified seçki + class-weighted CE **veya FocalLoss (gamma=2)** + val üzerinde logit-bias kalibrasyonu | `train.py` |
| Veri sızıntısı koruması | Kayıt bazlı split. Bu veri setinde her kayıt (JSxxxxx) ayrı bir bireydir → kayıt bazlı = hasta bazlı (şartname 5. Aşama "external validation" için ayrı strateji dahil) | `train.py`: `stratified_split` |
| Baseline model | El yapımı ritim/morfoloji özellikleri (~40 boyut) + HistGradientBoosting → macro F1 referans noktası | `ai-core/app/ecg/features.py`, `train.py baseline` |
| Ana model | ECGResNet-1D (~2.2M param): 12×2500 girdi → 3 sınıf; CPU eğitilebilir (aarch64 doğrulandı) | `ai-core/app/ecg/model.py`, `ai-core/models/ecg_resnet.pt` |
| XAI | Grad-CAM 1D (zaman × derivasyon odağı) + olasılık barları; viewer overlay | `model.py`, `frontend/components/EcgPanel.tsx` |
| **7.2** — Final **external validation** (TEKNOFEST'e özgün yeni anonim set, %90 görev puanı) | Eksternal validasyon stratejisi: gürültü/baseline-wander senaryoları + **05.05.2026 resmi verisiyle** gerçek external koşu (kod hazır, veri gelince `robustness`/`external` modunu çalıştır) | `train.py robustness`, `docs/teknik-rapor.md` |
| **7.1.2 / 7.7** — PDR: teknik rapor + çalıştırılabilir, yeniden üretilebilir, dokümante kod | Teknik rapor, tek komutla yeniden üretim (`scripts/run_eval.sh` + CI workflow), sonuç dosyaları commit'li | `docs/teknik-rapor.md`, `.github/workflows/train.yml` |

## Platform / Ürün Zorunlulukları

| Şartname Maddesi | Uygulama | Kanıt / Konum |
|---|---|---|
| KVKK uyumu — minimum veri | İstemci tarafı anonimleştirme (DICOM tag temizliği, .hea PHI temizliği, epikriz PII maskeleme); sunucuya ham PHI hiç gitmez | `frontend/lib/browser-anonymizer.ts` |
| KVKK uyumu — sunucu tarafı | .hea başlığı: SHA256 pseudonym, yaş bandı, cinsiyet silme, Dx korunur | `anonymizer/ecg_deid/deidentifier.py` |
| Zero-knowledge mimari | EKG `.hea` sunucuya asla gönderilmez; yalnız temizlenmiş önizleme istemcide | `frontend/app/studies/new/page.tsx` |
| MDR / SaMD human-in-the-loop | Her analiz `PENDING_REVIEW`; hekim kararı olmadan rapor kesinleşmez; audit log | `backend/app/api/v1/studies.py`, `analyses.py` |
| RBAC | admin / hekim / radyolog / asistan; karar yalnız hekim+radyolog | `backend/app/core/deps.py` |
| Audit trail | Oluşturma, analiz, karar olayları IP + kullanıcı ile | `services/audit.py` |

## Test Kapsamı

- `anonymizer/tests`: DICOM 6, PII 25, EKG-deid 7 test fonksiyonu (parametrizasyonla ilgili vaka kapsamı genişler; PII vaka sayısı 34)
- `ai-core/tests`: core 10, EKG çekirdek 14 (labels, preprocess)
- `backend/tests`: API 8
- CI'de `pytest` ile doğrulanır → `.github/workflows/train.yml` test adımı

## Demo Akışı (EKG)

1. Hekim giriş yapar
2. "Yeni Çalışma" → **EKG Kaydı** seçilir, `.mat` + `.hea` yüklenir → .hea tarayıcıda temizlenir
3. Sunucuya yalnız `.mat` gider → `/v1/ecg/analyze` → sınıf + güven + XAI
4. Viewer: 12 derivasyon dalga formu + Grad-CAM şeridi + olasılık barları
5. Hekim onayı → rapor kesinleşir, audit yazılır