# Hastane Devreye Alma Kılavuzu (Pulsar-KKDS)

Bu belge, sistemin bir hastanede yürürlüğe girmesi durumunda işleyişi,
rolleri ve üretim öncesi kontrol listesini açıklar.

## 1. Çalışma Akışı (vaka yolu)

```
Görüntü/Sinyal (CR, CT, EKG)          Epikriz metni
        │                                    │
        ▼                                    ▼
  [1] Anonimleştirme ──► anon_study_hash     masked_epikriz (PII taranır)
        │                                    │
        └──────────────┬─────────────────────┘
                       ▼
  [2] POST /v1/studies            (kayıt; KVKK: kimlik yok)
                       ▼
  [3] POST /v1/studies/{id}/analyze
        ├── ai-core /vision : bulgu olasılıkları + XAI haritaları
        ├── ai-core /nlp    : aciliyet skoru + vurgulanmış tokenlar
        ├── ai-core /ecg    : ritim sınıfı + güven
        └── ai-core /fusion : risk = 0.6*vision + 0.4*nlp
                       ▼
  [4] Analiz PENDING_REVIEW olarak kaydedilir (MDR: otomatik karar YOK)
                       ▼
  [5] Hekim viewer'da inceler → ONAYLA / REDDET (+not)
        • Karar verilebilir tek rol: hekim, radyolog, admin (asistan değil)
        • Karar audit-log'a değişmez zaman damgasıyla yazılır
                       ▼
  [6] Rapor kesinleşir (APPROVED) — benzer vakalar embedding ile önerilir
```

## 2. Roller

| Rol | Yetkiler |
|-----|----------|
| asistan | çalışma yükleyebilir, görüntüleyebilir; **karar veremez** |
| hekim / radyolog | analiz onaylama/red (+asistanın tüm yetkileri) |
| admin | kullanıcı açma (`POST /v1/auth/users`, gövde ile), denetim kaydı |

Şifreler: `POST /v1/auth/password` ile kullanıcı kendisi değiştirir.
Token: access 30 dk + refresh (gün); `POST /v1/auth/refresh`.

## 3. Üretim Öncesi Kontrol Listesi

**Zorunlu:**
- [ ] `JWT_SECRET` env değişkeni benzersiz değere ayarlanmalı (varsayılanı kullanmak token'ları tahmin edilebilir yapar — başlangıçta uyarı loglanır)
- [ ] SQLite → PostgreSQL (çoklu istemci/yazma kilidi). `DATABASE_URL` env ile.
- [ ] HTTPS zorunlu (tunnel/Vercel zaten TLS; kurum içi dağıtımda reverse-proxy TLS)
- [ ] Demo hesapları silinmeli / şifreleri değiştirilmeli
- [ ] Yedekleme: DB günlük yedek + `data/ecg_uploads` dizini

**Önerilen:**
- [ ] Rate-limit / brute-force koruması (login endpoint'i için)
- [ ] Log toplama (audit tablosu + uygulama logları merkezi SIEM'e)
- [ ] Model sürümleme: her analysis çıktısına model versiyonu alanı eklemek (MDR teknik dosya)
- [ ] PACS/HL7-FHIR entegrasyonu: worklist'ten çalışma açma, raporu RIS'e yazma
- [ ] Kesinti senaryosu: ai-core erişilemezse backend 503 döner; hasta bakışı manuel sürer

## 4. Bilinen Sınırlar (dürüst envanter)

- Vision motoru kural-tabanlıdır (özellik eşikleri gerçek PA grafilerine göre kalibre edildi);
  patoloji sınıflaması demo düzeyindedir, tanısal iddia taşımaz.
- EKG .mat doğrulaması içerik bazlı değildir; bozuk dosya 503 döner.
- Karar sonrası analiz kesinleşmiştir; yeni bakış için yeniden analiz gerekir (yeni PENDING satırı).
- Çoklu kurum/kiracı desteği, olgu silme (KVKK saklama süresi sonu imhası) yol haritasındadır.

## 5. Denetim Kaydı

`audit_logs` tablosuna yazılan olaylar: LOGIN, LOGIN_FAILED, USER_CREATED,
PASSWORD_CHANGED, STUDY_CREATED, ANALYSIS_CREATED, DECISION_APPROVED,
DECISION_REJECTED. Her kayıt user_id + IP + UTC zaman damgası taşır.
