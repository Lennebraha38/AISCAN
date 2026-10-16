# Bilinen Sınırlar ve Dürüst Konumlandırma — Pulsar-KKDS

Bu belge, Pulsar-KKDS'nin **ne olduğunu ve ne olmadığını** açıkça tanımlar.
İnceleme ve jüri değerlendirmelerinde yanlış beklenti oluşmaması için okunması
zorunludur.

## Konumlandırma

- Pulsar-KKDS bir **SaMD hedefli karar destek prototipidir**; onaylanmış bir
  tıbbi cihaz (SaMD) **değildir**, klinik üretim için hazır **değildir**.
- Sistem, **KVKK ilkeleri gözetilerek tasarlanmış** bir prototiptir; "KVKK
  uyumlu" ifadesi bir uygunluk belgesi/güvence olarak yorumlanmamalıdır.
- AI çıktısı **hekim onayı olmadan kesinleşmez** (human-in-the-loop); nihai
  klinik karar sorumluluğu hekimdedir.

## Klinik kanıt düzeyi

- Raporda kullanılan test seti **küçüktür** (≈80 kayıt) ve **dış doğrulama
  (external validation) yoktur**. Metrikler yarışma/prototip düzeyindedir.
- Sınıf bazlı performans dengesizdir; özellikle **blok sınıfı recall** düşüktür.
  Bu, klinik açıdan kritik bir hata profili oluşturur.
- Hasta-bazlı split ve sabit/izlenebilir test seti uygulanır (deterministik
  tohum), ancak farklı merkez/cihaz dağılımına genelleme **gösterilmemiştir**.
- Sınıf bazlı güven aralıkları ve hata analizi raporlanır
  (`docs/metrics/*.json` → `per_class`, `error_analysis`, `split`).

## Modality olgunluğu

| Modality | Durum | Not |
|---|---|---|
| **EKG (ana görev)** | Gerçek ML hattı | ECGResNet-1D, 12 derivasyon; yukarıdaki kanıt sınırları geçerli |
| **Görüntü (radyoloji)** | **Demo heuristiği** | Varsayılan yol, eğitilmiş bir radyoloji modeli DEĞİL; klasik görüntü öznitelikleri. Checkpoint varsa opsiyonel olarak devreye girer. Klinik performans metriği yoktur. |
| **NLP (epikriz)** | **Kural/sezgisel analiz** | Türkçe anahtar-kelime ve olumsuzlama kuralları; eğitilmiş klinik NLP modeli DEĞİL. |
| **Füzyon** | Basit risk birleştirme | Ağırlıklı skor; klinik olarak doğrulanmamıştır. |

## Gizlilik / anonimleştirme sınırları

Anonimleştirme "defense in depth" yaklaşımıyla yapılır ancak **tam kapsamlı
olduğu garanti edilmez**:

- **DICOM:** Seçili PHI tag'leri, private tag'ler ve **iç içe (nested)
  sequence'ler** özyinelemeli temizlenir. Buna karşın:
  - **Burn-in pixel metni** (görüntüye gömülü hasta adı/tarih) ve
  - kimi üretici-özel (private) yapılar
  tam otomatik tespit edilemeyebilir. Burn-in text için ayrı bir politika/manuel
  doğrulama gerekir.
- **PNG/JPEG:** EXIF/XMP/ICC ve metin (text/iTXt) meta verileri istemcide
  temizlenir. Yine de **görüntü üzerine basılmış (burned-in) yazı** ve piksel
  içine gömülü kimlik tespit edilemez.
- **WFDB `.hea`:** Kimlik alanları pseudonymlenir; `.hea` sunucuya hiç
  gönderilmez. `.mat` sinyal verisi kimlik taşımaz varsayılır.
- **Epikriz:** PII maskeleme + sunucu tarafı ikinci kontrol (PII reddi).

## Operasyonel sınırlar

- Model/artifact'ların eğitim hattı tarafından doğrudan `main` dalına
  commit edilmesi sürümleme açısından risklidir; artifact'lar release süreciyle
  yönetilmelidir.
- Uzun (Teknofest-Eval) eğitim hattı bu ortamda uçtan uca yeşil olarak
  doğrulanmamıştır.
- Frontend E2E (Playwright) gerçek servislerle CI'da koşturulur; ancak demo
  verisine bağımlıdır.

## Yasal / düzenleyici

- MDR (EU 2017/745) ve KVKK açısından nihai sınıflandırma ve uygunluk
  değerlendirmesi bir **onaylanmış kuruluşa** aittir. Bu depo yalnızca bir
  prototip ve teknik kanıt sunar; hiçbir düzenleyici onay iddiası taşımaz.
