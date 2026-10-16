# MDR (EU 2017/745) SaMD Sınıflandırma Beyanı — Pulsar-KKDS

> Bu belge, projenin **hedeflediği** düzenleyici konumu açıklar. Pulsar-KKDS
> onaylanmış bir tıbbi cihaz **değildir**; SaMD hedefli bir **karar destek
> prototipidir**. Klinik kanıt ve anonimleştirme sınırları için bkz.
> [SINIRLAMALAR.md](SINIRLAMALAR.md).

## 1. Sınıflandırma

Pulsar-KKDS, Tıbbi Cihaz Yönetmeliği (MDR) kapsamında **Software as a Medical
Device (SaMD)** hedefiyle geliştirilmiş bir karar destek prototipidir:

- **Amaç:** Radyolojik görüntü ve epikriz metninden **karar destek** sağlamak
  (risk skorlaması, ön bulgu listesi, benzer vaka önerisi).
- **Sınıflandırma gerekçesi (MDR Annex VIII, Rule 11):** Yazılım, teşhis veya
  tedavi kararını **tek başına vermez**; klinik kararın **girdisini** sunar.
  Çıktı, hekim tarafından doğrulanmadan hiçbir klinik süreçte kesinleşmez.
- **Sonuç:** Karar destek amacı ve human-in-the-loop kontrolü ile sınıf
  IIa altı **hedeflenir**; bu bir iddia/plan beyanıdır ve nihai sınıflandırma
  yalnızca yetkili bir uygunluk değerlendirmesi kuruluşu tarafından yapılabilir.
  Bu depo hiçbir düzenleyici onay taşımaz.

## 2. Human-in-the-Loop Kontrol Mimarisi

| Kontrol | Katman | Uygulama |
|---|---|---|
| Analiz asla otomatik kesinleşmez | Veritabanı | `analyses.status` yalnız `PENDING_REVIEW` ile doğar; `APPROVED`/`REJECTED` geçişi yalnız onay endpoint'iyle |
| Nihai karar yetkisi | API | `POST /v1/analyses/{id}/decision` — yalnız `hekim`/`radyolog` rolü (403 otherwise) |
| Karar değiştirilemez | Veritabanı | `review_decisions` append-only; ikinci karar denemesi 409 döner |
| İzlenebilirlik | Audit | Her karar `DECISION_APPROVED/REJECTED` action'ıyla audit log'a yazılır |
| Arayüz zorunluluğu | UI | Onay bloğu tamamlanmadan rapor "kesinleşti" gösterilmez; durum rozeti görünür |

## 3. Dil ve Sunum Kuralları (Risk Kontrolü)

1. Arayüzde "teşhis" ifadesi kullanılmaz; "ön bulgu", "risk skoru", "hekim
   değerlendirmesi önerilir" dili kullanılır.
2. Tüm sayfalarda kalıcı uyarı bandı: *"Bu sistem SaMD hedefli bir Karar Destek
   Prototipidir. Nihai klinik karar hekim sorumluluğundadır."*
3. AI çıktıları her zaman açıklanabilirlik verisiyle (Grad-CAM ısı haritası,
   token attribution, gerekçe metni) birlikte sunulur — hekim körü körüne
   onaylamaz.

## 4. Açıklanabilirlik (XAI) — Kullanıcı Hatası Riskinin Azaltılması

- Görsel bulgular için Grad-CAM/enerji saliency ısı haritası (%40 opaklık overlay)
- Epikriz için token düzeyinde risk vurgulaması + negasyon işaretleme
- Füzyon skorunun ağırlık dağılımının (%60 görüntü / %40 epikriz) açık beyanı

## 5. Kalite ve Doğrulama Kanıtları

- Birim/entegrasyon testleri: `backend/tests`, `ai-core/tests`, `anonymizer/tests`
- Uçtan uca senaryo testi: `frontend/e2e/flow.spec.ts`
- Deterministik çıkarım motoru: aynı girdi → aynı çıktı (`test_vision_deterministic`)
