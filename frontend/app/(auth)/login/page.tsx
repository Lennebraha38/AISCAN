"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setTokens } from "../../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("hekim@pulsar.demo");
  const [password, setPassword] = useState("hekim-demo-1234");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const tokens = await api.login(email, password);
      setTokens(tokens);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Giriş başarısız");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="container" style={{ maxWidth: 420, marginTop: 60 }}>
      <div className="card">
        <h1 style={{ marginTop: 0 }}>Pulsar-KKDS Giriş</h1>
        <p style={{ color: "#66708a", fontSize: 14 }}>
          KVKK uyumlu klinik karar destek platformu
        </p>
        <form onSubmit={onSubmit}>
          <input
            type="email"
            placeholder="E-posta"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <input
            type="password"
            placeholder="Şifre"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          {error && <p style={{ color: "#c0392b", fontSize: 13 }}>{error}</p>}
          <button className="btn" disabled={loading} type="submit">
            {loading ? "Giriş yapılıyor..." : "Giriş Yap"}
          </button>
        </form>
        <hr style={{ border: "none", borderTop: "1px solid #edf0f6", margin: "16px 0" }} />
        <small style={{ color: "#8a93ab" }}>
          Demo: hekim@pulsar.demo / hekim-demo-1234 · admin@pulsar.demo / admin-demo-1234
        </small>
      </div>
    </main>
  );
}
