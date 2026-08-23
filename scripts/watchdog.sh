#!/bin/bash
# Pulsar-KKDS bekcisi: olen servisleri ve tuneli her 60 sn'de bir yeniden baslatir.
# Kurulum (cron): * * * * * /root/projeler/pulsar-kkds/scripts/watchdog.sh
P=/root/projeler/pulsar-kkds
L=/tmp/opencode

# 1) ai-core (8001)
curl -s -m 3 -o /dev/null http://localhost:8001/health || \
  setsid nohup $P/.venv/bin/uvicorn app.main:app --port 8001 --app-dir "$P/ai-core" >> $L/aicore.log 2>&1 < /dev/null &

# 2) backend (8000)
curl -s -m 3 -o /dev/null http://localhost:8000/health || {
  pgrep -f "[u]vicorn app.main:app --host" | xargs -r kill 2>/dev/null
  setsid nohup env DATABASE_URL=sqlite:///$P/data/pulsar.db AI_CORE_URL=http://localhost:8001 \
    ECG_UPLOAD_DIR=$P/data/ecg_uploads \
    CORS_ORIGINS='["http://localhost:3000","http://192.168.1.102:3000","https://pulsar-kkds.vercel.app","https://pulsar-kkds-*.vercel.app"]' \
    $P/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir "$P/backend" >> $L/api.log 2>&1 < /dev/null &
}

# 3) frontend (3000)
curl -s -m 3 -o /dev/null http://localhost:3000/login || {
  pgrep -f "[n]ext-server" | xargs -r kill 2>/dev/null
  ( cd $P/frontend && setsid nohup npx next start -p 3000 -H 0.0.0.0 >> $L/web.log 2>&1 < /dev/null & )
}

# 4) tunel: surec yoksa yenisi + .env.production guncelle
if [ "$(pgrep -f '[c]loudflared tunnel' | wc -l)" = "0" ]; then
  setsid nohup $L/cloudflared tunnel --url http://localhost:8000 --protocol http2 >> $L/tunnel.log 2>&1 < /dev/null &
  sleep 8
  URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" $L/tunnel.log | tail -1)
  [ -n "$URL" ] && printf 'NEXT_PUBLIC_API_URL=%s\n' "$URL" > $P/frontend/.env.production && \
    echo "$(date) yeni tunel: $URL" >> $L/watchdog.log
fi

# 5) tunel adresi degistiyse Vercel'i arka planda yeniden deploy et (10 dk'da bir kere)
STAMP=$L/.vercel_deploy_stamp
if [ -f "$STAMP" ]; then
  [ $(($(date +%s) - $(stat -c %Y "$STAMP"))) -lt 600 ] && exit 0
fi
if [ -n "$(find $P/frontend/.env.production -newer $STAMP 2>/dev/null)" ] || [ ! -f "$STAMP" ]; then
  touch "$STAMP"
  ( cd $P/frontend && VERCEL_TELEMETRY_DISABLED=1 CI=1 setsid nohup \
      /usr/bin/vercel deploy --prod --yes >> $L/vercel-deploy.log 2>&1 < /dev/null & )
  echo "$(date) vercel redeploy tetiklendi" >> $L/watchdog.log
fi
exit 0
