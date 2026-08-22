# Pulsar-KKDS → EKG Platformu Pivot Planı

## Bağlam (Şartname Analizi)
- **Yarışma:** TEKNOFEST Sağlıkta Yapay Zekâ 2026 — **Lise Seviyesi / Kardiyoloji**
- **Görev:** 12 derivasyonlu EKG → 3 üst sınıf (Ritim Bozuklukları / İletim Bozuklukları / Normal EKG), multi-class tek tahmin
- **Metrik:** macro F1-score (ön eleme VE final); karışıklık matrisi + öğrenme eğrisi + sınıf bazlı hata analizi incelenir
- **Aşama 2:** fine-grained alt sınıflar (AFIB/AFL/AT/SVT/APB/VPB | LBBB/RBBB/AVB tipleri) — PSR sonrası kesin liste açıklanır
- **Veri:** PhysioNet ECG Arrhythmia 1.0.0 (45k kayıt, 500 Hz, 10 sn, .mat/.hea, SNOMED-CT Dx etiketleri)
- **Final:** external validation — TEKNOFEST'e özgün yeni EKG setiyle genelleme testi
- **Eski radyoloji modülü kapsam dışı** (şartname: "radyolojiden farklı olarak"); platform katmanı (KVKK, audit, RBAC, onay workflow'u) korunur.

## Faz A — Veri Altyapısı
- [x] A1: `ai-core/ecg/data.py` — PhysioNet indirici: .hea etiket taraması (async httpx), stratified .mat indirme, resume destekli
- [x] A2: `ai-core/ecg/labels.py` — SNOMED→3 üst sınıf haritası; çoklu etiket önceliği: Aritmi > İletim Bozukluğu > Normal (belgeli); hedef dışı kod stratejisi
- [x] A3: `ai-core/ecg/preprocess.py` — baseline wander kaldırma, 0.5–40 Hz bant geçiren, 50 Hz notch, sabit 10sn@500Hz, derivasyon bazlı z-skor
- [x] A4: Hasta-bazlı (kayıt-bazlı) split train/val/test — veri sızıntısı yok; external validation için ayrık hold-out

## Faz B — Model ve XAI
- [x] B1: Baseline: el yapımı özellikler (HR, RR istatistikleri, QRS/PR/QT morfolojisi) + sklearn — macro F1 referans noktası
- [x] B2: 1D ResNet CNN (torch 2.13, cp314 aarch64): 12×5000 girdi → 3 sınıf; class-weighted CE (dengesizlik)
- [ ] B3: Eğitim scripti: macro F1, karışıklık matrisi PNG, öğrenme eğrileri, sınıf bazlı rapor
- [x] B4: Grad-CAM 1D saliency: zaman ekseni × derivasyon ısı haritası ("kararı hangi beat sürükledi")
- [ ] B5: Aşama 2 hazırlığı: hiyerarşik alt-sınıf kafası iskeleti (üst sınıf → alt tanı)

## Faz C — Platform Entegrasyonu
- [x] C1: `anonymizer/ecg_deidentifier` — .hea PHI temizliği (#Age/#Sex pseudonymize, Dx korunur) + pii_nlp epikriz entegrasyonu
- [x] C2: ai-core `/v1/ecg/analyze` endpoint: sinyal → ön işleme → tahmin + güven + saliency overlay
- [x] C3: Backend Study modeli EKG uyarlaması (sinyal dosyası, fs, derivasyon meta) — audit/RBAC/onay akışı aynı
- [x] C4: Frontend viewer: 12 derivasyon dalga formu render + saliency overlay + SaMD uyarı bandı + onay bloğu
- [x] C5: Testler: preprocess, labels, deidentifier, API entegrasyon

## Faz D — Dokümantasyon ve Teslim
- [ ] D1: Şartname uyum matrisi (her madde → implementasyon kanıtı)
- [ ] D2: Teknik rapor: metodoloji, macro F1 sonuçları, external validation stratejisi
- [ ] D3: Demo senaryosu güncelleme (EKG akışı)
- [ ] D4: README güncelleme + commit + GitHub push (AISCAN)

## Ortam Notları
- torch 2.13.0 cp314 aarch64 PyPI'dan kuruluyor (download.pytorch.org 403 verir, KULLANMA)
- PhysioNet HTTPS erişimi açık; S3 alternatifi: physionet-open bucket
- pip komutlarını ASLA pipe'la çalıştırma (takılır) → `> log 2>&1` sonra oku
