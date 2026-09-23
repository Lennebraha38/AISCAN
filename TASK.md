# Pulsar-KKDS → EKG Platformu Pivot Planı

## Bağlam (Şartname Analizi)
- **Yarışma:** TEKNOFEST Sağlıkta Yapay Zekâ 2026 — **Lise Seviyesi / Kardiyoloji**
- **Görev:** 12 derivasyonlu EKG → 3 üst sınıf (Ritim Bozuklukları / İletim Bozuklukları / Normal EKG), multi-class tek tahmin
- **Metrik:** macro F1-score (ön eleme VE final); karışıklık matrisi + öğrenme eğrisi + sınıf bazlı hata analizi incelenir
- **Aşama 2:** fine-grained alt sınıflar (AFIB/AFL/AT/SVT/APB/VPB | LBBB/RBBB/AVB tipleri) — PSR sonrası kesin liste açıklanır
- **Veri:** PhysioNet ECG Arrhythmia 1.0.0 (45.152 kayıt, 500 Hz, 10 sn, .mat/.hea, SNOMED-CT Dx etiketleri) — şartname 3.1.1 ile birebir
- **Final:** external validation — TEKNOFEST'e özgün yeni EKG setiyle genelleme testi (şartname 7.2, görev puanı %90)
- **Eski radyoloji modülü kapsam dışı** (şartname: "radyolojiden farklı olarak"); platform katmanı (KVKK, audit, RBAC, onay workflow'u) korunur.

## Faz A — Veri Altyapısı
- [x] A1: `ai-core/ecg/data.py` — PhysioNet indirici: .hea etiket taraması (async httpx), stratified .mat indirme, resume destekli
- [x] A2: `ai-core/ecg/labels.py` — SNOMED→3 üst sınıf haritası; çoklu etiket önceliği: Aritmi > İletim Bozukluğu > Normal (belgeli); hedef dışı kod stratejisi
- [x] A3: `ai-core/ecg/preprocess.py` — baseline wander kaldırma, 0.5–40 Hz bant geçiren, 50 Hz notch, sabit 10 sn; eğitim/inference 250 Hz'e yeniden örnekleme, derivasyon bazlı z-skor
- [x] A4: Kayıt bazlı split (bu veri setinde kayıt = birey → hasta bazlı) train/val/test — veri sızıntısı yok; external validation için ayrık hold-out ve fold değerlendirmesi

## Faz B — Model ve XAI
- [x] B1: Baseline: el yapımı özellikler (HR, RR istatistikleri, QRS/PR/QT morfolojisi) + sklearn — macro F1 referans noktası (bias kalibrasyonlu)
- [x] B2: 1D ResNet CNN (torch, aarch64 CPU): 12×2500 girdi → 3 sınıf; class-weighted CE veya FocalLoss (dengesizlik), augmentasyon
- [x] B3: Eğitim scripti: macro F1, karışıklık matrisi PNG, öğrenme eğrileri, sınıf bazlı rapor; sinif bazlı logit-bias kalibrasyonu (val); 5-fold kararlılık raporu
- [x] B4: Grad-CAM 1D saliency: zaman ekseni × derivasyon ısı haritası ("kararı hangi beat sürükledi") + input saliency
- [x] B5: Aşama 2 desteği: donmuş backbone üzerinde superclass-bazlı fine-grained alt kafalar (`train.py stage2`); nadir alt gruplar 'other' olarak gruplanır
- [x] B6: Robustness: gürültü (SNR kademesi) + baseline wander senaryoları → `docs/metrics/robustness_metrics.json`

## Faz C — Platform Entegrasyonu
- [x] C1: `anonymizer/ecg_deidentifier` — .hea PHI temizliği (#Age/#Sex pseudonymize, Dx korunur) + pii_nlp epikriz entegrasyonu
- [x] C2: ai-core `/v1/ecg/analyze` endpoint: sinyal → ön işleme → tahmin + güven + saliency overlay
- [x] C3: Backend Study modeli EKG uyarlaması (sinyal dosyası, fs, derivasyon meta) — audit/RBAC/onay akışı aynı
- [x] C4: Frontend viewer: 12 derivasyon dalga formu render + saliency overlay + SaMD uyarı bandı + onay bloğu
- [x] C5: Testler: preprocess, labels, deidentifier, API entegrasyon

## Faz D — Dokümantasyon ve Teslim
- [x] D1: Şartname uyum matrisi (her madde → implementasyon kanıtı) — `docs/sartname-uyum-matrisi.md`
- [x] D2: Teknik rapor: metodoloji, macro F1 sonuçları (katlı + test + robustness), external validation stratejisi — `docs/teknik-rapor.md`
- [x] D3: Demo senaryosu güncelleme (EKG akışı) — `docs/demo-senaryosu.md`
- [x] D4: README güncelleme + commit + GitHub push (AISCAN)

## Ortam Notları
- torch (aarch64 CPU) PyPI'dan kuruluyor; CUDA görünürlüğü gerekmiyor (CPU eğitimi)
- PhysioNet HTTPS erişimi açık; indirme resume destekli (`.part`)
- pip komutlarını ASLA pipe'la çalıştırma (takılır) → `> log 2>&1` sonra oku
- `ai-core/models/` gitignore'da; model/konfig yeniden üretilebilir (`make`/`train.py`) — teslim öncesi force-add edilir