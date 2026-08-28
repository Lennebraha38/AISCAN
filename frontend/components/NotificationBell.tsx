"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useNotifications } from "../lib/notifications";

export default function NotificationBell() {
  const { notifications, connected } = useNotifications();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    const actionCount = notifications.filter(
      (n) => n.type === "analysis_completed" || n.type === "patient_report_generated" || n.type === "decision"
    ).length;
    setUnread(actionCount);
  }, [notifications]);

  const requestPermission = () => {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  };

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button
        onClick={() => { setOpen(!open); requestPermission(); }}
        style={{
          background: "none", border: "none", cursor: "pointer", fontSize: 18,
          color: connected ? "#2456d6" : "#8a93ab", position: "relative", padding: "4px 8px",
        }}
        title={connected ? "Bildirimler canli" : "Bildirim baglantisi yok"}
      >
        🔔
        {unread > 0 && (
          <span style={{
            position: "absolute", top: 0, right: 0, background: "#c0392b",
            color: "#fff", borderRadius: 10, fontSize: 10, width: 16, height: 16,
            display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700,
          }}>
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div style={{
          position: "absolute", right: 0, top: "100%", marginTop: 8, width: 320,
          background: "#fff", border: "1px solid #e0e4ed", borderRadius: 10,
          boxShadow: "0 8px 32px rgba(0,0,0,.12)", zIndex: 100, maxHeight: 360, overflow: "auto",
        }}>
          <div style={{ padding: "10px 14px", borderBottom: "1px solid #eef0f5", fontWeight: 600, fontSize: 13 }}>
            Bildirimler
            <span style={{ float: "right", fontSize: 11, color: connected ? "#1e8e4e" : "#c0392b" }}>
              {connected ? "● Canli" : "● Kesik"}
            </span>
          </div>
          {notifications.length === 0 && (
            <div style={{ padding: 20, textAlign: "center", color: "#8a93ab", fontSize: 13 }}>
              Henuz bildirim yok
            </div>
          )}
          {notifications.slice(0, 15).map((n) => (
            <div
              key={n._key}
              style={{
                padding: "8px 14px", borderBottom: "1px solid #f5f7fb", fontSize: 12,
                cursor: n.analysis_id ? "pointer" : "default",
              }}
              onClick={() => {
                if (n.analysis_id) {
                  window.location.href = `/viewer/${n.study_id || ""}?analysis=${n.analysis_id}`;
                }
              }}
            >
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ color: n.type === "decision" ? "#2456d6" : n.type === "analysis_completed" ? "#1e8e4e" : n.type === "analysis_started" ? "#b7791f" : "#8a93ab" }}>
                  {n.type === "decision" ? "💬" : n.type === "analysis_completed" ? "✅" : n.type === "analysis_started" ? "⏳" : n.type === "patient_report_generated" ? "📋" : "ℹ️"}
                </span>
                <span style={{ fontWeight: 500 }}>
                  {n.type === "decision"
                    ? `Karar: ${n.decision === "APPROVED" ? "Onay" : "Red"}`
                    : n.type === "analysis_completed"
                      ? `Analiz tamamlandi (risk: ${n.fusion_risk_score?.toFixed(1) ?? "?"})`
                      : n.type === "analysis_started"
                        ? "Analiz baslatildi"
                        : n.type === "patient_report_generated"
                          ? "Hasta raporu uretildi"
                          : "Sistem"}
                </span>
              </div>
              {n.reviewer && (
                <div style={{ color: "#66708a", marginTop: 2 }}>{n.reviewer}</div>
              )}
            </div>
          ))}
          <Link
            href="/approvals"
            onClick={() => setOpen(false)}
            style={{ display: "block", textAlign: "center", padding: 10, fontSize: 12, color: "#2456d6", borderBottom: "none" }}
          >
            Tumunu Gor
          </Link>
        </div>
      )}
    </div>
  );
}
