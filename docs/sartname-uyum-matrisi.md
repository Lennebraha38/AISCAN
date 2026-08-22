# Şartname Uyum Matrisi — Pulsar-KKDS

**Yarışma:** TEKNOFEST 2026 — Yapay Zekâ ile Sağlıkta Devrim Yarışması
**Kategori Seçimi:** Lise — Kardiyoloji / EKG Ritim Analizi
**Not:** Üniversite+ kategorisindeki genetik varyant problemi kapsam dışında tutulmuş; lise şartnamesindeki EKG sınıflandırma görevi tam kapsamda yürütülmüştür.

## Görev Tanımı ↔ Uygulama

| Şartname Maddesi | Uygulama | Kanıt / Konum |
|---|---|---|
| EKG sinyallerinin 3 üst sınıfa sınıflandırılması: **Aritmiler**, **İletim Bozuklukları**, **Normal** | SNOMED CT kodlarından üst sınıf haritası; çoklu etikette **blok > aritmi > normal** önceliği (veri analizi ile gerekçeli) | `ai-core/app/ecg/labels.py` |
| Veri seti: PhysioNet ECG Arrhythmia Database (ptbxl benzeri WFDB) | 45.152 kayıt tarandı, 42.625 etiketli kayıt eşleştirildi, stratified seçki: 15.983 | `data/ecg/manifest.jsonl`, `selected.jsonl` |
| Başarı ölçütü: **macro F1** | Tüm eğitim/validasyon döngüsü macro F1 ile optimize ve raporlanır | `ai-core/app/ecg/train.py` |
| Ön işleme | Bazal salınım kaldırma → 0.5–40 Hz Butterworth → 50 Hz notch → derivasyon bazlı z-skor → sabit 10 sn @ 500 Hz | `ai-core/app/ecg/preprocess.py` |
| Sınıf dengesizliği | class-weighted CrossEntropy + stratified split | `train.py` (deep), `data.py` (seçki) |
| Veri sızıntısı koruması | Kayıt-bazlı (hasta-bazlı) split; aynı hastanın kayıtları tek parçada | `preprocess.py` / `train.py` split fonksiyonu |
| Baseline model | El yapımı ritim/morfoloji özellikleri (HR, RR istatistikleri, QRS/PR/QT) + sklearn LogisticRegression | `ai-core/app/ecg/features.py` |
| Ana model | ECGResNet-1D (~2M param): 12×5000 girdi → 3 sınıf, torch 2.13 CPU eğitilebilir | `ai-core/app/ecg/model.py` |
| XAI zorunluluğu | Grad-CAM 1D (zaman × karar odağı) + derivasyon saliency matrisi; viewer'da görsel katman | `model.py`, `frontend/components/EcgPanel.tsx` |
| Model güvenilirliği / OOD | Gürültü enjeksiyonlu robustness değerlendirmesi (SNR kademesi) | `train.py robustness` |

## Platform / Ürün Zorunlulukları

| Şartname Maddesi | Uygulama | Kanıt / Konum |
|---|---|---|
| KVKK uyumu — minimum veri | İstemci tarafı anonimleştirme (DICOM tag temizliği, .hea PHI temizliği, epikriz PII maskeleme); sunucuya ham PHI hiç gitmez | `frontend/lib/browser-anonymizer.ts` (`cleanDicom`, `cleanHea`, `maskEpikriz`) |
| KVKK uyumu — sunucu tarafı | .hea başlığı: SHA256 pseudonym, yaş bandı (10'lu), cinsiyet silme, Dx korunur | `anonymizer/ecg_deid/deidentifier.py` (+7 test) |
| Zero-knowledge mimari | EKG `.hea` dosyası sunucuya **asla gönderilmez**; temizlenmiş önizleme yalnızca istemcide gösterilir | `frontend/app/studies/new/page.tsx` |
| MDR / SaMD human-in-the-loop | Her analiz `PENDING_REVIEW`; hekim ONAYLA/REDDET kararı olmadan rapor kesinleşmez; karar audit log'a yazılır | `backend/app/api/v1/studies.py:130`, `analyses.py` |
| Değişmez zaman damgası | Onay anında UTC timestamp + kullanıcı kimliği ile `review_decisions` kaydı | `models`, `audit.py` |
| RBAC (rol tabanlı erişim) | admin / hekim / radyolog / asistan rolleri; karar verme yalnız hekim+radyolog | `backend/app/core/deps.py` (`DECISION_ROLES`) |
| Audit trail | Çalışma oluşturma, analiz, karar olayları IP + kullanıcı ile loglanır | `services/audit.py` |
| Benzer vaka desteği | Embedding tabanlı `/v1/analyses/{id}/similar` | `services/embeddings.py` |
| Erişilebilir arayüz | Türkçe UI, klavye erişilebilir formlar, renk+kod ikili gösterim (renk körlüğü dostu) | `frontend/` |

## Demo Akışı (EKG)

1. Hekim giriş yapar (`hekim@pulsar.demo`)
2. "Yeni Çalışma" → çalışma türü **EKG Kaydı** seçilir
3. `.mat` + `.hea` yüklenir → tarayıcıda .hea temizlenir, rapor ekranda canlı listelenir
4. Sunucuya yalnız `.mat` gider → ai-core `/v1/ecg/analyze` → sınıf + güven + KHD + XAI
5. Viewer: 12 derivasyon dalga formu + Grad-CAM şeridi + derivasyon saliency + olasılık barları
6. Hekim onayı → rapor kesinleşir, audit yazılır

## Test Kapsamı (81 test, tümü yeşil)

- `anonymizer/tests`: DICOM 9, PII 34, EKG-deid 7
- `ai-core/tests`: vision/nlp 10, EKG çekirdek 14 (labels, preprocess, features, model, inference)
- `backend/tests`: API entegrasyon 8 (auth, study, analyze, decide, signal)
