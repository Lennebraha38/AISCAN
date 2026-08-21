# Pulsar-KKDS — Görev Planı (TASK.md)

> **Bu dosya AI kodlama ajanları (Codex / OpenCode) için ana çalışma planıdır.**
> Her görev `[ ]` işaretli checkbox ile listelenmiştir. Bir görevi bitiren ajan
> `[x]` yapmalı ve "DoD" (Definition of Done) kriterlerini doğrulamalıdır.
> Yeni görev eklerken mevcut numaralandırmayı bozmayın.

---

## 0. Proje Özeti

**Pulsar-KKDS**: Özel hastaneler ve radyologlar için SaaS klinik karar destek sistemi.
Akciğer X-Ray/CT taramaları + Türkçe hasta epikriz raporlarını eş zamanlı analiz ederek
risk skorlaması ve anomali tespiti yapar.

### Jüri Tam Puan Stratejisi (3 sütunlu mimari)

| Sütun | Gereksinim | Uygulama |
|---|---|---|
| **KVKK (6698) + Kişisel Sağlık Verileri Yönetmeliği** | Zero-Knowledge Architecture | Veri sunucuya gitmeden önce **istemci tarafında** DICOM metadata (Hasta Adı, TC, Doğum Tarihi) ve epikriz PII'si temizlenir. Sunucuya yalnız anonim veri ulaşır. |
| **MDR (EU 2017/745)** | SaMD sınıflandırması | Sistem "Teşhis Koyan" DEĞİL, "Karar Destek Sistemi (SaMD)" olarak konumlanır. **Human-in-the-Loop**: AI çıktısı hekim onaylamadan kesinleşmez. Arayüzde zorunlu hekim onay mekanizması. |
| **XAI (Açıklanabilir Yapay Zeka)** | Kara kutu yok | Görsel: **Grad-CAM** ısı haritaları. Metin: risk oluşturan kelimelerin vurgulanması (token-level attribution). |

### Teknoloji Yığını

- **Modül 1:** Python, pydicom, WASM (Rust→wasm-bindgen opsiyonel), Turkish NLP (spaça tr model / Zemberek-NLP / custom regex+NER)
- **Modül 2:** PyTorch, Vision Transformer (ViT) / ResNet50, Grad-CAM (`pytorch-grad-cam`), Türkçe Medical-BERT (BERTurk / dbmdz fine-tune)
- **Modül 3:** FastAPI, PostgreSQL + pgvector, JWT (python-jose), SQLAlchemy, Alembic
- **Modül 4:** Next.js (App Router), Cornerstone.js (cornerstone-core + cornerstone-wado-image-loader), TailwindCSS, shadcn/ui

---

## 1. Monorepo Dizin Yapısı (ÖNCE BUNU KUR)

```
pulsar-kkds/
├── TASK.md                      # bu dosya
├── README.md
├── docker-compose.yml           # postgres(+pgvector), api, web
├── .env.example
├── docs/
│   ├── kvkk-uyum-matrisi.md     # veri akış şeması + uyum kanıtları
│   └── mdr-samd-beyani.md       # SaMD sınıflandırma & human-in-the-loop dokümanı
├── backend/                     # Modül 3 (FastAPI)
│   ├── app/
│   │   ├── main.py
│   │   ├── core/                # config, security(JWT), deps
│   │   ├── models/              # SQLAlchemy modelleri
│   │   ├── schemas/             # Pydantic şemaları
│   │   ├── api/v1/              # router'lar
│   │   └── services/            # ai_client, audit_log
│   ├── alembic/
│   ├── tests/
│   └── pyproject.toml
├── ai-core/                     # Modül 2 (PyTorch inference servisi)
│   ├── app/
│   │   ├── main.py              # FastAPI inference API (:8001)
│   │   ├── vision/              # ViT/ResNet + Grad-CAM
│   │   ├── nlp/                 # Medical-BERT epikriz analizi
│   │   └── schemas.py
│   ├── scripts/train/           # eğitim scriptleri (demo için opsiyonel)
│   ├── tests/
│   └── pyproject.toml
├── anonymizer/                  # Modül 1 (istemci tarafı)
│   ├── dicom_cleaner/           # pydicom tabanlı DICOM anonimizasyon kütüphanesi
│   │   └── wasm/                # Rust/WASM port (tarayıcıda çalıştırma)
│   ├── pii_nlp/                 # Türkçe PII maskeleme kütüphanesi
│   └── tests/
└── frontend/                    # Modül 4 (Next.js)
    ├── app/
    │   ├── (auth)/login/
    │   ├── dashboard/
    │   ├── viewer/[studyId]/    # Cornerstone DICOM viewer + Grad-CAM overlay
    │   └── approvals/           # Hekim onay paneli
    ├── lib/
    │   ├── anonymizer-client.ts # Modül1 WASM/kütüphane köprüsü
    │   └── api.ts
    └── components/
```

---

## 2. SERT KISITLAR (Tüm modüllerde geçerli — İHLAL = RED)

1. **PII asla sunucuya gitmez.** Backend/AI-Core'a gelen her istek zaten anonimleştirilmiş olmalı. Backend'de `patient_id` yerine yalnız `anon_study_hash` (SHA-256 salted) kullanılır.
2. **AI çıktısı asla otomatik kesinleşmez.** Her analiz kaydı `PENDING_REVIEW` durumunda doğar; yalnızca hekim onayıyla (`APPROVED`/`REJECTED`) nihaileşir. Bu kural DB seviyesinde ve UI seviyesinde zorunludur.
3. **Her işlem audit log'a yazılır** (kim, ne zaman, hangi veri hash'i, ne yaptı). Log kayıtları immutabledir (UPDATE/DELETE yok).
4. **AI arayüzde "karar destek" dili kullanır**: "teşhis" kelimesi UI'da geçmez; "ön bulgu", "risk skoru", "hekim değerlendirmesi önerilir" dili kullanılır.
5. Tüm endpoint'ler JWT korumalı; rol bazlı erişim: `admin`, `hekim`, `radyolog`, `asistan`.

---

## 3. FAZ 0 — İskelet Kurulum

### T0.1 Repo iskeleti
- [x] Yukarıdaki dizin yapısını oluştur; her pakete minimal `pyproject.toml` / `package.json` ekle.
- [x] `docker-compose.yml`: `postgres` (pgvector uzantılı `pgvector/pgvector:pg16` imajı), `api` (:8000), `ai-core` (:8001), `web` (:3000).
- [x] `.env.example` oluştur (DB URL, JWT_SECRET, AI_CORE_URL). Gerçek secret commit ETME.
- [x] README.md: kurulum adımları (`docker compose up` tek komutla ayağa kalkmalı).

**DoD:** `docker compose up` sonrası 4 servis sağlıklı yanıt veriyor (`/health` endpoint'leri 200).

---

## 4. FAZ 1 — Modül 1: Client-Side Anonymizer

> Amaç: KVKK tam puanı. Hiçbir kişisel veri ağdan geçmez.

### T1.1 DICOM Metadata Temizleyici (`anonymizer/dicom_cleaner`)
- [x] `pydicom` ile DICOM dosyasını aç, DICOM PS3.15 tanımlı **tüm personal information tag'larını** temizle:
  - Zorunlu temizlenecekler: `(0010,0010)` PatientName, `(0010,0020)` PatientID, `(0010,0030)` BirthDate, `(0010,0040)` Sex, `(0008,0080)` InstitutionName, `(0008,1030)` StudyDescription, `(0008,103E)` SeriesDescription, `(0010,1000)` OtherPatientIDs, özel tag'lar.
- [x] Temizlik stratejisi: `keep` / `replace-hashed` / `remove` üçlü modu. Hasta takibi için `PatientID → SHA256(salt+id)` pseudonymization.
- [x] Çıktı: yeni anonim DICOM byte stream + temizlenen alanların raporu (`{"removed": [...], "hashed": [...]}`) — bu rapor UI'da kullanıcıya gösterilecek (şeffaflık).
- [x] Birim testleri: gerçekçi örnek DICOM fixture'ları ile tüm PHI tag'larının temizlendiğini doğrula (`tests/test_dicom_cleaner.py`).

**DoD:** `pytest anonymizer/tests -k dicom` yeşil; anonim çıktıda PHI tag scan sıfır hata.

### T1.2 Türkçe PII Maskeleme (`anonymizer/pii_nlp`)
- [x] Türkçe epikriz metninden PII tespiti:
  - **Regex katmanı:** TC Kimlik No (11 hane + checksum algoritması!), telefon, e-posta, T.C. pasaport no, tarih desenleri, plaka.
  - **NER katmanı:** kişi adı-soyadı, hastane/kurum adı, adres, hekim adları (spaCy `tr_core_news` veya kural tabanlı fallback).
- [x] Maskeleme formatı: `[TC_KIMLIK]`, `[TELEFON]`, `[KISI_ADI]`, `[KURUM]`... (maskelenen tür korunur ki NLP modeli bağlamı yitirmesin).
- [x] `mask(text) -> (masked_text, findings[])` API'si; `findings` UI'da vurgulama için span bilgisi içersin (`start`, `end`, `type`).
- [x] Test: 20+ gerçekçi Türkçe epikriz örneği ile recall testi.

**DoD:** TC kimlik checksum'lı test vakalarının %100 yakalanıyor; `pytest` yeşil.

### T1.3 Tarayıcı Tarafı Entegrasyon Hazırlığı
- [x] **KARAR:** WASM yerine TypeScript portu birincil yol seçildi (`frontend/lib/browser-anonymizer.ts` — gerçek DICOM tag temizleme + PII maskeleme, tarayıcıda çalışır). WASM sözleşmesi `anonymizer/dicom_cleaner/wasm/README.md`'de belgelendi.
- [x] ~~`dicom_cleaner` mantığının WASM portu (Rust + `wasm-bindgen` + `dicom-rs`) **veya** Pyodide fallback (pydicom wheel'i Pyodide'de çalıştırma). Karar: WASM birincil, Pyodide fallback.
- [x] `frontend/lib/anonymizer-client.ts`: tarayıcıda dosya seçildiği anda anonimizasyonu tetikleyen köprü modülü. Network tab'ında ham dosyanın hiç gönderilmediğini doğrulayan e2e testi.

**DoD:** Tarayıcıda yüklenen DICOM/epikriz, anonimleştirilmeden hiçbir HTTP isteğinin body'sinde görünmüyor (Playwright network assert).

---

## 5. FAZ 2 — Modül 2: AI Core & XAI Engine

> Amaç: XAI jüri tam puanı. Her çıktı açıklanabilir olmalı.

### T2.1 Vision Model Servisi (`ai-core/app/vision`)
- [x] Akciğer X-Ray sınıflandırma modeli: `torchvision` ResNet50 veya `timm` ViT-B/16, ChestX-ray14/CheXpert etiketleriyle fine-tune hazır script (`scripts/train/`). Demo için pretrained checkpoint yükleme desteği.
- [x] Çıktı: çok-etiketli olasılıklar (Atelektazi, Kardiomegali, Efüzyon, İnfiltrasyon, Kütle/Nodül, Pnömoni, Pnömotoraks...) + genel `risk_score` (0-100).
- [x] CT desteği: HU pencereleme (lung window) ön işleme fonksiyonu.

### T2.2 Grad-CAM XAI Katmanı
- [x] `pytorch-grad-cam` ile hem ResNet (son conv bloğu) hem ViT (son attention bloğunun reshape'lenmiş token haritası) için heatmap üretimi.
- [x] Heatmap'i orijinal görüntü üzerine bindirip PNG olarak döndür (base64) + her bulgu için ayrı CAM.
- [x] Yanıt şeması: `{findings: [{label, probability, cam_image_b64, top_regions[]}], risk_score}`.

**DoD:** `POST /v1/vision/analyze` örnek X-Ray ile heatmap üretiyor; heatmap görsel olarak anomali bölgesini gösteriyor (test fixture ile doğrulanmış).

### T2.3 Türkçe Medical-BERT Epikriz Analizi (`ai-core/app/nlp`)
- [x] `dbmdz/bert-base-turkish-cased` fine-tune iskeleti: klinik metinden risk sınıflandırması (ör. aciliyet: düşük/orta/yüksek).
- [x] **Metin XAI:** token-level attribution (Integrated Gradients veya attention rollout) ile risk oluşturan kelimeleri span + skor olarak döndür. Frontend bunları vurgulayacak.
- [x] Maskelenmiş epikrizle çalışır (PII içeremez); girdide PII pattern yakalanırsa isteği reddet (defans-in-depth).

**DoD:** `POST /v1/nlp/analyze` → `{urgency, confidence, highlighted_tokens:[{text,start,end,score}]}`; örnek epikrizde "toraks BT'de 8 mm nodül" gibi ifadeler yüksek skorla vurgulanıyor.

### T2.4 AI Core API Kabuğu
- [x] FastAPI (:8001): `/v1/vision/analyze`, `/v1/nlp/analyze`, `/v1/fusion` (görsel+metin skorlarını birleştirip tek risk skoru üreten basit ağırlıklı füzyon + gerekçe metni).
- [x] Model yükleme lazy/singleton; health endpoint'te model durumu raporlansın.
- [x] Girdi doğrulama: maksimum dosya boyutu, izinli MIME tipleri.

---

## 6. FAZ 3 — Modül 3: SaaS Backend & DB

> Amaç: MDR/Human-in-the-Loop mimarisi + audit trail.

### T3.1 Veritabanı Şeması (PostgreSQL + pgvector)
- [x] Tablolar:
  - `users` (id, email, password_hash(bcrypt/argon2), role[admin|hekim|radyolog|asistan], created_at)
  - `studies` (id, anon_study_hash UNIQUE, modality, image_count, created_by_id, created_at) — **PII kolonu YOK**
  - `analyses` (id, study_id FK, vision_result JSONB, nlp_result JSONB, fusion_risk_score NUMERIC, status[PENDING_REVIEW|APPROVED|REJECTED], created_at)
  - `review_decisions` (id, analysis_id FK, reviewer_id FK, decision[APPROVED|REJECTED], note TEXT, decided_at) — **Hekim Onay Log'u**
  - `audit_logs` (id, user_id, action, entity_type, entity_id, data_hash, ip, created_at) — append-only
  - `case_embeddings` (analysis_id FK, embedding vector(768)) — pgvector benzer vaka arama
- [x] Alembic migration'ları; `audit_logs` üzerinde UPDATE/DELETE engelleyen trigger.
- [x] Seed script: demo kullanıcılar (admin@demo / hekim@demo) + anonim demo çalışma.

### T3.2 Kimlik Doğrulama & Yetkilendirme
- [x] JWT access+refresh token (python-jose), rol bazlı dependency'ler (`require_role("hekim")`).
- [x] Şifre politikası, token süresi, refresh rotasyonu.

### T3.3 API Endpoint'leri (`backend/app/api/v1`)
- [x] `POST /v1/auth/login`, `POST /v1/auth/refresh`
- [x] `POST /v1/studies` — **yalnız anonimleştirilmiş** görüntü + maskelenmiş epikriz kabul eder; gelen payload'da PII regex taraması yapar, bulunursa 422 döner (defans-in-depth, log'a da "PII_REJECTED" action'ıyla yazılır).
- [x] `POST /v1/studies/{id}/analyze` — AI Core'a proxy atar, sonucu `PENDING_REVIEW` olarak kaydeder.
- [x] `GET /v1/analyses/{id}` — sonuç + XAI görselleri.
- [x] `POST /v1/analyses/{id}/decision` — SADECE `hekim`/`radyolog` rolü; `review_decisions`'a yazar, `analyses.status` günceller, audit log. **Bu endpoint olmadan analiz nihaileşmez (MDR kuralı).**
- [x] `GET /v1/cases/similar?analysis_id=` — pgvector cosine similarity ile benzer geçmiş vaka listesi (anonim).
- [x] `GET /v1/audit/logs` — sadece admin.
- [x] Tüm mutation endpoint'lerinde audit log middleware/hook.

**DoD:** pytest entegrasyon testleri: (1) PII içeren istek 422, (2) onaysız analiz `PENDING_REVIEW`, (3) asistan rolü decision veremez 403, (4) her çağrı audit log satırı üretiyor.

---

## 7. FAZ 4 — Modül 4: Frontend UI (Next.js)

> Amaç: Jüri demosu. KVKK şeffaflığı + Human-in-the-Loop görsel kanıtı.

### T4.1 Auth & Layout
- [x] Login sayfası, JWT'yi httpOnly cookie'de tutan middleware, rol bazlı menüler.
- [x] Dashboard: bekleyen onaylar, son analizler, risk dağılım grafikleri.

### T4.2 Anonimizasyon Şeffaf Ekranı (KVKK vitrin!)
- [x] Dosya yükleme ekranı: dosya seçilir seçilmez **istemcide** anonimizasyon koşar; ekranda "Temizlenen Alanlar" paneli canlı listelenir (Hasta Adı ✓ kaldırıldı, TC ✓ maskelendi...).
- [x] "Sunucuya yalnızca anonim veri iletilir" rozeti + teknik detay tooltip'i. Jüriye anlatılabilir tek ekran.

### T4.3 DICOM Viewer + Grad-CAM Overlay
- [x] Cornerstone.js entegrasyonu: WADO image loader, zoom/pan/window-level araçları.
- [x] Grad-CAM PNG'sini viewport üzerine %40 opaklıkta overlay; bulgu seçince ilgili CAM'e geçiş.
- [x] Bulgu listesi paneli: her bulgu için olasılık barı + "Bölgeyi göster" butonu.

### T4.4 Epikriz Analiz Paneli (Metin XAI)
- [x] Maskelenmiş epikriz metni; riskli token'lar renk skalasıyla (kırmızı=yüksek) vurgulu, hover'da skor.
- [x] Aciliyet kartı: düşük/orta/yüksek + güven skoru.

### T4.5 Hekim Onay Paneli (MDR vitrin!)
- [x] Analiz ekranının altında zorunlu karar bloğu: `ONAYLA` / `REDDET` + serbest not. Karar verilene kadar durum rozeti `⏳ HEKİM ONAYI BEKLİYOR`.
- [x] Karar sonrası değişmez zaman damgalı "Rapor Kesinleşti" görünümü + hekim imza bilgisi.
- [x] Sayfa geneli uyarı bandı: *"Bu sistem bir Karar Destek Sistemidir (SaMD). Nihai klinik karar hekim sorumluluğundadır."* (MDR dil uyumu).

**DoD:** Playwright e2e: yükle → anonim panelini doğrula → analiz → heatmap görünür → hekim onayı → durum APPROVED. Tüm akış tek testte.

---

## 8. FAZ 5 — Uyum Dokümantasyonu & Demo Paketi

- [x] `docs/kvkk-uyum-matrisi.md`: madde madde KVKK referansı ↔ teknik kontrol (veri minimizasyonu md.4, açık rıza md.5-6, teknik idari tedbirler md.12, veri işleme envanteri).
- [x] `docs/mdr-samd-beyani.md`: Rule 11 altında SaMD sınıflandırma gerekçesi, human-in-the-loop risk kontrol dokümanı.
- [x] Jüri demo senaryosu scripti (5 dk): anonimleştirme → analiz → XAI → onay → benzer vaka → audit log.
- [x] `docker compose up` ile tek komut demo; seed verili hazır durum.

---

## 9. Görev Sırası ve Bağımlılıklar

```
T0.1 ──► T1.1 ──► T1.2 ──► T1.3
   │
   ├──► T2.1 ──► T2.2 ──► T2.4
   │        └──► T2.3 ──┘
   │
   └──► T3.1 ──► T3.2 ──► T3.3 ──► T4.x ──► FAZ 5
```

- Paralelleştirme: Modül 1, 2, 3 bağımsız başlayabilir (farklı ajanlara dağıtılabilir).
- Modül 4, T3.3 API sözleşmesi netleşince başlar; mock API ile erken başlanabilir.

## 10. Ajan Talimatları (Codex/OpenCode için)

1. Her görevi kendi başlığındaki checkbox sırasına göre uygula; bitirdikçe `[x]` işaretle.
2. Kod yazarken yukarıdaki **SERT KISITLAR** bölümünü asla ihlal etme.
3. Her modülün testlerini çalıştır (`pytest`, `npm run test:e2e`) — kırmızı test bırakma.
4. Commit mesajı formatı: `modül(görev): kısa açıklama` → ör. `anonymizer(T1.1): DICOM PHI tag temizliği`.
5. Belirsizlik varsa bu dosyadaki strateji tablosunu (bölüm 0) referans al; jüri puanına en yakın kararı seç.
