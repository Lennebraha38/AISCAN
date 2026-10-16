import type { NextConfig } from "next";

// Guvenlik basliklari. CSP bilincli olarak "self + inline" tabanlidir:
// Next.js hidrasyon script'leri ve cornerstone web worker'lari (blob:)
// ile uyumlu kalmasi gerekir. Harici script/embed engellenir; XSS yuzeyi ve
// cerceveleme (clickjacking) kisitlanir.
const isDev = process.env.NODE_ENV !== "production";

const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""} blob:`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  // API farkli bir origin'de olabilir (NEXT_PUBLIC_API_URL) + SSE icin ws.
  "connect-src 'self' http: https: ws: wss:",
  "worker-src 'self' blob:",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
];

const nextConfig: NextConfig = {
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
