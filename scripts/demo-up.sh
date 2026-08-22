#!/bin/bash
# Pulsar-KKDS demo kurtarma: servisler + taze trycloudflare tuneli + Vercel yeniden deploy.
# Kullanim: bash /root/projeler/pulsar-kkds/scripts/demo-up.sh
set -u
P=/root/projeler/pulsar-kkds
LOG=/tmp/opencode

echo "[1/5] Servisler baslatiliyor..."
setsid "$LOG/start-all.sh" < /dev/null > /dev/null 2>&1
sleep 5

echo "[2/5] Eski tunel kapatiliyor, yenisini aciliyor..."
pgrep -f "[c]loudflared tunnel" | xargs -r kill 2>/dev/null
sleep 1
setsid nohup "$LOG/cloudflared" tunnel --url http://localhost:8000 > "$LOG/tunnel.log" 2>&1 < /dev/null &

URL=""
for i in $(seq 1 20); do
  sleep 2
  URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$LOG/tunnel.log" | head -1)
  [ -n "$URL" ] && break
done
if [ -z "$URL" ]; then echo "HATA: tunel URL alinamadi ($LOG/tunnel.log)"; exit 1; fi
echo "    tunel: $URL"

echo "[3/5] Saglik kontrol..."
# NOT: bu ortamin DNS'i taze subdomain'lerde kararsiz; once normal, sonra
# Cloudflare edge IP pinli --resolve ile dene (anycast: her IP hizmet verir).
HOSTONLY="${URL#https://}"
OK=""
for i in $(seq 1 10); do
  if curl -4 -s -m 8 -o /dev/null "$URL/health"; then OK=1; break; fi
  if curl -s -m 8 --resolve "$HOSTONLY:443:104.16.231.132" -o /dev/null "$URL/health"; then OK=1; break; fi
  sleep 2
done
[ -n "$OK" ] || { echo "HATA: tunel uzerinden backend erisilemiyor ($LOG/tunnel.log)"; exit 1; }

echo "[4/5] .env.production guncelleniyor ($URL)..."
printf 'NEXT_PUBLIC_API_URL=%s\n' "$URL" > "$P/frontend/.env.production"

echo "[5/5] Vercel yeniden deploy ediliyor (~1-2 dk)..."
cd "$P/frontend"
VERCEL_TELEMETRY_DISABLED=1 CI=1 vercel deploy --prod --yes > "$LOG/vercel-deploy.log" 2>&1
grep -E "Production|Aliased|Ready" "$LOG/vercel-deploy.log" | tail -3
echo "TAMAM: https://pulsar-kkds.vercel.app yeni API -> $URL"
