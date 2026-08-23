#!/bin/bash
# Her 60 sn'de bir watchdog.sh calistirir; kendisi olurse yeniden dogar (iki katman).
while true; do
  bash /root/projeler/pulsar-kkds/scripts/watchdog.sh >/dev/null 2>&1
  sleep 60
done
