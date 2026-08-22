# Jüri Demo Senaryosu (5 dakika)

**Ana senaryo: EKG (Lise/Kardiyoloji görevi).** Radyoloji akışı aynı mimaride
ikinci modality olarak çalışır; jüri isterse ekranın sağında paralel gösterilir.

## Ön hazırlık (demo öncesi 1 kez)

```bash
docker compose up -d --build          # postgres + api + ai-core + web
PYTHONPATH=backend .venv/bin/python backend/scripts/seed.py   # demo kullanıcılar
```

Web: http://localhost:3000 — giriş: `hekim@pulsar.demo / hekim-demo-1234`

Demo EKG dosyaları: PhysioNet WFDB örnek kayıtları (`.mat` + `.hea`) —
`data/ecg/selected.jsonl` içinden 2-3 kayıt önceden indirilmiş olarak hazırlanır.

## Akış

| Dakika | Adım | Jüriye anlatılan |
|---|---|---|
| 0:00 | Login → Panel | Rol bazlı erişim, bekleyen onay sayacı |
| 0:30 | **Yeni Çalışma → Çalışma Türü: EKG Kaydı** | Şartname görevi: 12 derivasyonlu WFDB sinyal. `.mat` + `.hea` seçilir |
| 0:50 | **KVKK vitrin (EKG):** .hea temizleme raporu | Kayıt kimliği SHA256 pseudonym, yaş → 10'luk bant, cinsiyet silindi, serbest metin maskelendi; **".hea dosyası sunucuya asla gitmez"** — DevTools Network sekmesinde tek istek: yalnız .mat |
| 1:30 | Epikriz metnini yapıştır | PII'ler anında `[TC_KIMLIK]`, `[KISI_ADI]` ile maskelenir; sunucuya gidecek metin şeffaf gösterilir |
| 2:00 | Kaydet ve Analiz Et | ai-core `/v1/ecg/analyze`: ön işleme → ECGResNet-1D tahmin + güven + KHD (kalp hızı) + fusion risk skoru |
| 2:30 | **Viewer — 12 Derivasyon + XAI katmanı** | **Ana vitrin:** dalga formları canvas'ta; kırmızı/sarı şerit = Grad-CAM 1D karar odağı ("model hangi beat'e baktı"); mavi zemin = derivasyon önemi; olasılık barları (Aritmi / İletim Bozukluğu / Normal) |
| 3:15 | Sınıf değişimi anlatımı | "XAI katmanı" kutusunu kapat-aç: modelin bakış açısını şeffaflaştırma — makro F1'in yanındaki yorumlanabilirlik taahhüdü |
| 3:45 | **Hekim Onayı** | **MDR vitrin:** "⏳ HEKİM ONAYI BEKLİYOR" rozeti → not yaz → ONAYLA → "RAPOR KESİNLEŞTİ". Asistan rolüyle deneyerek 403 alındığını göster |
| 4:15 | Benzer vakalar + Audit log + robustness | Embedding tabanlı benzer vaka listesi; audit log'da tüm adımlar; SNR kademesinde macro F1 dayanıklılık grafiği (`docs/metrics/`) |

## Kapanış cümlesi

"Pulsar-KKDS'te EKG sinyali hastaneden çıkmadan kimliksizleşir, model kararı
hangi beat'ten aldığını gösterir ve hiçbir rapor hekim onayı olmadan
kesinleşmez — KVKK, MDR ve XAI tek mimaride."

