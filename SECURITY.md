# Güvenlik Politikası — Pulsar-KKDS

## Kapsam ve konumlandırma

Pulsar-KKDS, TEKNOFEST 2026 için geliştirilmiş **SaMD hedefli bir karar destek
prototipidir**; üretilmiş/onaylanmış bir tıbbi cihaz değildir. Bu belge,
projenin güvenlik ve gizlilik duruşunu, bilinen sınırlarını ve bildirim akışını
tanımlar.

- **Güvenlik/gizlilik kontrolleri:** JWT kimlik doğrulama, rol tabanlı erişim
  (RBAC), `token_version` ile oturum iptali, IDOR kontrolleri, append-only audit
  log, istemci taraflı (tarayıcıda) anonimleştirme ve sunucu tarafı PII ikinci
  kontrolü.
- **Bilinen sınırlar:** `docs/SINIRLAMALAR.md` dosyasına bakın. Bu sınırlar
  giderilene kadar sistemin klinik üretim ortamında kullanılmaması gerekir.

## Desteklenen sürümler

Yalnızca `main` dalının en güncel hali güvenlik düzeltmeleri alır.

## Güvenlik açığı bildirimi

Lütfen güvenlik açıklarını **genel (public) issue olarak açmayın**.

1. GitHub üzerinden **özel güvenlik bildirimi** (Security → Report a
   vulnerability / Private vulnerability reporting) kullanın; veya
2. Depo yöneticisine doğrudan ulaşın.

Bildirimde şunları eklemeye çalışın:

- Etkilenen bileşen (anonymizer / ai-core / backend / frontend) ve sürüm/commit.
- Yeniden üretme adımları ve etki (gizlilik ihlali, yetki yükseltme, XSS, PHI
  sızması, hizmet reddi vb.).
- Varsa kanıt (istek/yanıt, ekran görüntüsü, PoC).

Yanıt hedefi: **72 saat içinde** ilk geri bildirim.

## Gizli bilgi sızıntısı (secret leak) durumu

`.env`, `JWT_SECRET`, `ANON_SALT` veya herhangi bir erişim token'ı sızarsa:

1. İlgili anahtarı **derhal döndürün (rotate)** ve token'ları iptal edin.
2. `token_version`'ı artıran bir şifre değişimi ile tüm eski oturumları düşürün.
3. Sızıntıyı ve alınan önlemi kayda geçin.

> Uyarı: Geliştirme kolaylığı için `.env` dosyalarında gerçek sır tutmayın;
> üretimde `PULSAR_ENV=production` ile güçlü `JWT_SECRET` / `ANON_SALT`
> zorunludur (uygulama zayıf varsayılanlarla **başlamaz**).

## Güvenli dağıtım kontrol listesi

- [ ] `PULSAR_ENV=production` ve ≥32 karakter rastgele `JWT_SECRET`, ≥16 karakter
      `ANON_SALT` ayarlandı.
- [ ] HTTPS zorunlu; `SECURE` çerez bayrakları etkin.
- [ ] `CORS_ORIGINS` yalnızca bilinen origin'leri içeriyor.
- [ ] `TRUST_FORWARDED_FOR` yalnızca güvenilir bir ters proxy arkasında `1`.
- [ ] Veritabanı yedekleme ve audit log saklama politikası tanımlı.
