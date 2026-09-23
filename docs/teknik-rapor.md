# Teknik Rapor — Pulsar-KKDS / AISCAN

**Yarışma:** TEKNOFEST 2026 Sağlıkta Yapay Zekâ — Lise Seviyesi / Kardiyoloji
**Görev:** 12 derivasyonlu EKG → {Ritim Bozukluğu, İletim Bozukluğu, Normal EKG} üst sınıf tahmini (multi-class, tek etiket)
**Metrik:** macro F1-score (şartname 3.1.2 / 7.2)

---

## 1. Yöntem

### 1.1 Veri
- **Kaynak:** PhysioNet **ECG Arrhythmia 1.0.0** (şartname 3.1.1'deki resmi örnek veri seti; 45.152 kayıt, 500 Hz, 10 sn, WFDB `.mat/.hea`, SNOMED-CT `#Dx` etiketleri).
- **Eşleştirme:** 45.152 kayıttan 42.625'inde `#Dx` etiketi doğrulandı; SNOMED-CT kodları `labels.py` haritasıyla üst sınıfa çevrildi. Çoklu etikette öncelik **iletişim bozukluğu > aritmi > normal** (hasta güvenliği: blok varlığında blok bildirilir).
- **Seçki:** Sınıf dengesine göre stratified **15.983** kayıt (blok 2.983 / aritmi 6.500 / normal 6.500).
- **Bölünme:** Kayıt bazlı 80/10/10 (train/val/test). Bu veri setinde her kayıt ayrı bir bireye aittir (JSxxxxx = birey), bu nedenle kayıt bazlı bölünme hasta-bazlıdır ve bireyler arası sızıntı yoktur. Değerlendirme kararlılığı için ayrıca 5-katlı (folds) rapor üretilir.

### 1.2 Ön İşleme
`preprocess.py`: bazal salınım kaldırma → 0.5–40 Hz Butterworth bant geçiren → 50 Hz şebeke (notch) → derivasyon bazlı z-skor → sabit 10 sn (500 Hz'den **250 Hz'e** yeniden örnekleme → 12×2500 girdi). Zaman kaydırma, amplituv/lead ölçekleme ve Gauss gürültüsü eğitim sırasında augmentasyon olarak uygulanır.

### 1.3 Modeller
| Model | Açıklama | Rol |
|---|---|---|
| Baseline | El yapımı ~40 özellik (HR, RR istatistikleri, QRS/PR/QT morfolojisi) + HistGradientBoosting | Referans alt sınır |
| Ana model | **ECGResNet-1D** (~2.2M param, 12×2500): stem + 4 stage (32→256 kanal) + global pool + 3 sınıf head | Teslim edilen model |
| 2. aşama (fine-grained) | Donmuş backbone üzerinde superclass-bazlı alt kafalar (AFIB/AFL/AT/SVT/APB/VPB | LBBB/RBBB/AVB...); nadir alt gruplar `other` | Şartname 3.1.2 ikinci aşama |

### 1.4 Kayıp ve Kalibrasyon
- Sınıf dengesizliği → **FocalLoss** (γ=2, sınıf-ağırlıklı alpha) veya class-weighted CrossEntropy (label-smoothing 0.05).
- AdamW (lr 3e-4, cosine) + grad-clip 5.0 + erken durdurma (patience=8).
- **Logit-bias kalibrasyonu:** val setinde macro F1'i maksimize eden sınıf-bazlı bias, koordinat aramasıyla üretilir ve test/robustness'ta uygulanır (kalibrasyon test setini görmez).
- 5-katlı değerlendirme ile knife-dağılım raporu (mean ± std).

## 2. Sonuçlar

Sayısal çıktılar (`docs/metrics/*.json`), figürler (`docs/figures/`) ve model (`ai-core/models/`) bu raporla aynı commit'te taşınır:

| Çıktı | Dosya |
|---|---|
| Deep model test sonuçları (macro F1 raw/tuned, report, confusion matrix, learning curves, fold tablosu) | `docs/metrics/deep_metrics.json` |
| Baseline referans | `docs/metrics/baseline_metrics.json` |
| Robustness (gauss 0.05/0.10/0.20, baseline wander) | `docs/metrics/robustness_metrics.json` |
| 2. aşama alt-grup sonuçları | `docs/metrics/stage2_metrics.json` |
| Karışıklık matrisi + öğrenme eğrileri | `docs/figures/*.png` |

Yorum kriterleri (şartname 3.1.2): sınıf-bazlı hataya bakılır — hedef, blok sınıfında recall'un (aritmiye kaçan kayıtların azaltılması) diğer sınıflardan geride kalmamasıdır.

## 3. Yeniden Üretilebilirlik

CI (`.github/workflows/train.yml`) veya tek komut (`scripts/run_eval.sh`) ile uçtan uca yeniden üretilir:

```
fetch (.mat) → build-cache → baseline → deep (--folds 5) → robustness → stage2
```

Ortam: Python 3.11, PyTorch CPU (x86_64 runner / aarch64 doğrulandı), numpy/scipy/scikit-learn. Cihaz içi depolama kullanmaz (veri indirme ve eğitim uzakta çalışır).

## 4. External Validation Stratejisi (şartname 7.2)

1. **Mevcut (kod hazır):** gürültü (SNR kademesi) ve baseline-wander senaryolarıyla OOD dayanıklılığı (`robustness_metrics.json`).
2. **05.05.2026 resmi veri paylaşımı sonrası:** Gizlilik Taahhütnamesi imzasıyla alınan TEKNOFEST setindeki doğrulanmış kayıtlar, eğitim hattından tamamen dışarıda tutulan ayrı bir klasöre konur ve `deep`/`baseline` eval aynı script ile koşulur → final metrik (görev puanı %90).
3. **Final (festival alanı):** TEKNOFEST'e özgün, anonimleştirilmiş yeni set üzerinde aynı checkpoint ile tek geçiş. Hiçbir eğitim sırasında bu setle temas olmaz (erken durdurma dahil val kararları bu setten bağımsızdır).

## 5. Uyum Özeti (kısa)

- Veri seti, görev tanımı ve macro F1 metriği → şartname ile birebir.
- 2. aşama fine-grained alt-grup modeli → teslim edildi (`stage2`).
- PDR gereksinimi: teknik rapor + çalıştırılabilir/dokümante kod + sonuç dosyaları → bu raporda ve CI'de.
- KVKK/etik: veri tamamen anonim (PhysioNet), işleme açık, model sonuçları hekim onayına tabi (human-in-the-loop).