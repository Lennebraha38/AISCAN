# Sentetik demo EKG kayıtları

Bu dizindeki `.mat` / `.hea` dosyaları **gerçek hasta verisi değildir**.
`scripts/gen_demo_ecg.py` tarafından matematiksel olarak üretilmiş sentetik
12‑derivasyonlu EKG dalga formlarıdır; yalnızca arayüz/entegrasyon demolarında
ve birim testlerinde kullanılmak üzere sağlanır.

| Kayıt | Ritim | SNOMED‑CT (Dx) | Açıklama |
|-------|-------|----------------|----------|
| `SX00001` | normal | 426783006 | Düzenli sinüs ritmi |
| `SX00002` | afib   | 164889003 | Düzensiz RR (atrial fibrilasyon profili) |
| `SX00003` | lbbb   | 164909002 | Geniş, çentikli QRS (sol dal bloğu profili)

> Bu kayıtlar PhysioNet ECG‑Arrhythmia kayıtlarıyla **karıştırılmamalıdır**;
> kimlikler `SXxxxxx` olup yalnızca demo amaçlıdır. Her `.hea` dosyasında
> `#Synthetic: true` işareti bulunur.

Yeniden üretmek için:

```bash
python scripts/gen_demo_ecg.py data/ecg/demo
```
