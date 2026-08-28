"use client";
/**
 * SSE bildirim istemcisi — karar olaylarini canli olarak dinler.
 * NotificationProvider icinde kullanilir.
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { API_URL, getTokens } from "./api";

export interface Notification {
  type: "decision" | "connected" | "keepalive" | "analysis_started" | "analysis_completed" | "patient_report_generated";
  analysis_id?: string;
  study_id?: string;
  decision?: string;
  reviewer?: string;
  risk_score?: number;
  fusion_risk_score?: number;
  user?: string;
  ts: number;
  _key?: number;
}

interface NotificationCtx {
  notifications: Notification[];
  critical: Notification | null;
  clearCritical: () => void;
  connected: boolean;
}

const Ctx = createContext<NotificationCtx>({
  notifications: [],
  critical: null,
  clearCritical: () => {},
  connected: false,
});

export function useNotifications() {
  return useContext(Ctx);
}

let _keySeq = 0;

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [critical, setCritical] = useState<Notification | null>(null);
  const [connected, setConnected] = useState(false);
  const evtRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const tokens = getTokens();
    if (!tokens) return;

    const url = `${API_URL}/v1/notifications`;
    // EventSource destegi sinirli — fetch + ReadableStream ile SSE okuyacagiz.
    const ctrl = new AbortController();
    let alive = true;

    (async () => {
      try {
        const resp = await fetch(url, {
          headers: { Authorization: `Bearer ${tokens.access_token}` },
          signal: ctrl.signal,
        });
        if (!resp.ok || !resp.body) return;
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";

        if (alive) setConnected(true);

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split("\n");
          buf = lines.pop() || "";
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const data = JSON.parse(line.slice(6)) as Notification;
              if (data.type === "keepalive") continue;
              data._key = ++_keySeq;
              setNotifications((prev) => [data, ...prev].slice(0, 50));
              // Kritik bulgu: risk >=70 ise
              if (data.type === "decision" && (data.risk_score ?? 0) >= 70) {
                setCritical(data);
              }
              // Tarayici bildirimleri
              if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
                if (data.type === "analysis_completed") {
                  new Notification("Analiz Tamamlandi", { body: `Risk: ${data.fusion_risk_score?.toFixed(1) ?? "?"}` });
                } else if (data.type === "patient_report_generated") {
                  new Notification("Hasta Raporu Hazir", { body: `PDF uretildi: ${data.analysis_id?.slice(0,8)}` });
                }
              }
            } catch {}
          }
        }
      } catch {}
      if (alive) setConnected(false);
    })();

    return () => {
      alive = false;
      ctrl.abort();
      setConnected(false);
    };
  }, []);

  const clearCritical = useCallback(() => setCritical(null), []);

  return (
    <Ctx.Provider value={{ notifications, critical, clearCritical, connected }}>
      {children}
    </Ctx.Provider>
  );
}
