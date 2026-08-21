# Jüri Demo Senaryosu (5 dakika)

## Ön hazırlık (demo öncesi 1 kez)

```bash
docker compose up -d --build          # postgres + api + ai-core + web
PYTHONPATH=backend .venv/bin/python backend/scripts/seed.py   # demo kullanıcılar
```

Web: http://localhost:3000 — giriş: `hekim@pulsar.demo / hekim-demo-1234`

## Akış

| Dakika | Adım | Jüriye anlatılan |
|---|---|---|
| 0:00 | Login → Panel | Rol bazlı erişim, bekleyen onay sayacı |
| 0:30 | **Yeni Çalışma** ekranına DICOM yükle | **KVKK vitrin:** "Temizlenen Alanlar" paneli canlı akar — Hasta Adı/TC/Doğum tarihi kaldırıldı/hash'lendi. "Ham dosya ağa çıkmıyor" vurgusu. Tarayıcı DevTools Network sekmesi kanıtı |
| 1:30 | Epikriz metnini yapıştır | PII'ler anında `[TC_KIMLIK]`, `[KISI_ADI]` ile maskelenir; sunucuya gidecek metin şeffaf gösterilir |
| 2:00 | Kaydet ve Analiz Et | Backend defans-in-depth: maskelenmemiş PII gelse bile 422 reddi (test kanıtı) |
| 2:30 | **Viewer** ekranı | **XAI vitrin:** Grad-CAM ısı haritası %40 opaklıkta overlay; bulgu listesi olasılık barları; "Bölgeyi Göster" ile odak değişimi |
| 3:15 | Epikriz XAI paneli | Riskli kelimeler kırmızı vurgulu, hover'da katkı skoru; negasyon mavi işaretli; aciliyet kartı |
| 3:45 | **Hekim Onayı** | **MDR vitrin:** "⏳ HEKİM ONAYI BEKLİYOR" rozeti → not yaz → ONAYLA → "RAPOR KESİNLEŞTİ". Asistan rolüyle deneyerek 403 alındığını göster |
| 4:15 | Benzer vakalar + Audit log | pgvector benzer vaka listesi; admin olarak audit log'da tüm iz bırakan adımlar |

## Kapanış cümlesi

"Pulsar-KKDS'te veri hastaneden çıkmadan kimliksizleşir, AI asla kara kutu
değildir ve hiçbir çıktı hekim onayı olmadan kesinleşmez — KVKK, MDR ve XAI
tek mimaride."
