/** Backend API istemcisi. */

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api";

export interface Tokens {
  access_token: string;
  role: string;
}

export function getTokens(): Tokens | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("pulsar_tokens");
  return raw ? (JSON.parse(raw) as Tokens) : null;
}

export function setTokens(tokens: Tokens): void {
  // Yalnızca kısa ömürlü access token saklanır. Refresh token ARTIK burada
  // tutulmaz; HttpOnly + Secure + SameSite çerezde taşınır (XSS ile uzun
  // ömürlü oturum token'ı çalınmasını zorlaştırır).
  localStorage.setItem("pulsar_tokens", JSON.stringify(tokens));
  // Middleware'in okuyabilmesi için işaret çerezi. Bu yalnızca bir bayraktır
  // (token değeri taşımaz); HttpOnly sunucu tarafından set edilemediğinden JS
  // yazar; yine de Secure + SameSite=Strict eklenir.
  const secure = typeof location !== "undefined" && location.protocol === "https:" ? "; secure" : "";
  document.cookie = `pulsar_auth=1; path=/; max-age=86400; samesite=strict${secure}`;
}

export function clearTokens(): void {
  localStorage.removeItem("pulsar_tokens");
  const secure = typeof location !== "undefined" && location.protocol === "https:" ? "; secure" : "";
  document.cookie = `pulsar_auth=; path=/; max-age=0; samesite=strict${secure}`;
}

async function request<T>(path: string, init: RequestInit = {}, allowRefresh = true): Promise<T> {
  const tokens = getTokens();
  const headers = new Headers(init.headers);
  if (tokens) headers.set("Authorization", `Bearer ${tokens.access_token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let resp: Response;
  try {
    // credentials: "include" → HttpOnly refresh çerezi gönderilir/alınır.
    resp = await fetch(`${API_URL}${path}`, { ...init, headers, credentials: "include" });
  } catch {
    throw new Error(
      `Sunucuya ulaşılamıyor (${API_URL}). Bağlantıyı ve servis durumunu kontrol edin.`
    );
  }
  if (
    resp.status === 401 &&
    allowRefresh &&
    path !== "/v1/auth/login" &&
    path !== "/v1/auth/refresh"
  ) {
    // Kısa ömürlü access token süresi dolmuş olabilir: refresh çereziyle bir
    // kez yenile, sonra isteği tekrarla. Başarısızsa oturumu kapat.
    if (await tryRefresh()) {
      return request<T>(path, init, false);
    }
    clearTokens();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("Oturum süresi doldu");
  }
  if (!resp.ok) {
    let detail = "";
    try {
      detail = (await resp.json()).detail ?? "";
    } catch {}
    if (!detail) {
      detail =
        resp.status >= 500 || resp.status === 530
          ? "Sunucu şu anda yanıt vermiyor, lütfen tekrar deneyin."
          : `İstek başarısız (${resp.status})`;
    }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

let refreshInFlight: Promise<boolean> | null = null;

/** HttpOnly çerezdeki refresh token ile access token'ı yeniler. */
function tryRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const r = await fetch(`${API_URL}/v1/auth/refresh`, {
          method: "POST",
          credentials: "include",
        });
        if (!r.ok) return false;
        const data = (await r.json()) as { access_token: string; role?: string };
        const current = getTokens();
        setTokens({ access_token: data.access_token, role: data.role ?? current?.role ?? "" });
        return true;
      } catch {
        return false;
      }
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

export const api = {
  login: (email: string, password: string) =>
    request<Tokens>("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ status: string }>("/v1/auth/logout", { method: "POST" }),
  me: () => request<{ id: string; email: string; role: string }>("/v1/auth/me"),
  listStudies: () =>
    request<
      { id: string; anon_study_hash: string; modality: string; created_at: string; has_epikriz: boolean }[]
    >("/v1/studies"),
  getStudy: (id: string) =>
    request<{
      id: string;
      anon_study_hash: string;
      modality: string;
      created_at: string;
      analyses: { id: string; status: string; fusion_risk_score: number }[];
    }>(`/v1/studies/${id}`),
  createStudy: (body: Record<string, unknown>) =>
    request<{ id: string }>("/v1/studies", { method: "POST", body: JSON.stringify(body) }),
  analyzeStudy: (studyId: string, file: Blob, filename: string) => {
    const form = new FormData();
    form.append("image", file, filename);
    return request<{ analysis_id: string; status: string; fusion_risk_score: number }>(
      `/v1/studies/${studyId}/analyze`,
      { method: "POST", body: form },
    );
  },
  analyzeEcgStudy: (studyId: string, file: Blob, filename: string) => {
    const form = new FormData();
    form.append("signal_file", file, filename);
    return request<{ analysis_id: string; status: string; fusion_risk_score: number }>(
      `/v1/studies/${studyId}/analyze`,
      { method: "POST", body: form },
    );
  },
  /** Epikriz-only akış: dosya olmadan yalnızca maskelenmiş metinle analiz çalıştırır. */
  analyzeStudyText: (studyId: string) =>
    request<{ analysis_id: string; status: string; fusion_risk_score: number }>(
      `/v1/studies/${studyId}/analyze`,
      { method: "POST" },
    ),
  getAnalysis: (id: string) =>
    request<{
      id: string;
      study_id: string;
      status: string;
      fusion_risk_score: number;
      vision_result: VisionResult | null;
      nlp_result: NlpResult | null;
      ecg_result: EcgResult | null;
      decisions: { decision: string; note: string | null; decided_at: string }[];
    }>(`/v1/analyses/${id}`),
  getCam: (
    id: string,
    opts?: { finding?: string; clean?: boolean },
  ) => {
    const q = new URLSearchParams();
    if (opts?.finding) q.set("finding", opts.finding);
    if (opts?.clean) q.set("clean", "1");
    const qs = q.toString();
    return request<{
      label: string | null;
      requested_label?: string;
      cam_image_b64: string;
      xai_method?: string;
      empty?: boolean;
    }>(`/v1/analyses/${id}/cam${qs ? `?${qs}` : ""}`);
  },
  getEcgSignal: (id: string) =>
    request<EcgSignal>(`/v1/analyses/${id}/signal`),
  decide: (id: string, decision: "APPROVED" | "REJECTED", note?: string) =>
    request<Record<string, unknown>>(`/v1/analyses/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, note }),
    }),
  listAnalyses: (status?: string) =>
    request<
      { id: string; study_id: string; status: string; fusion_risk_score: number;
        created_at: string; modality?: string | null; top_finding?: string | null }[]
    >(`/v1/analyses${status ? `?status_filter=${status}` : ""}`),
  getPatientReport: (id: string) => {
    const tokens = getTokens();
    return fetch(`${API_URL}/v1/analyses/${id}/patient.pdf`, {
      headers: tokens ? { Authorization: `Bearer ${tokens.access_token}` } : {},
      credentials: "include",
    }).then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.blob(); });
  },
  secondOpinion: (id: string, note: string) =>
    request<{ ok: boolean }>(`/v1/analyses/${id}/second-opinion`, {
      method: "POST",
      body: JSON.stringify({ decision: "APPROVED", note }),
    }),
  getDashboardStats: () =>
    request<{
      total_analyses: number;
      pending_reviews: number;
      last_24h: { total: number; approved: number; rejected: number; high_risk: number };
    }>("/v1/dashboard/stats"),
};

export interface VisionFinding {
  label: string;
  probability: number;
  cam_image_b64: string | null;
  top_regions: { row: number; col: number; energy: number }[];
}

export interface VisionResult {
  findings: VisionFinding[];
  risk_score: number;
  features: Record<string, number>;
  xai_method: string;
  /** Dürüstlük etiketi: "heuristic-demo" (eğitilmemiş) veya "checkpoint". */
  engine?: string | null;
}

export interface HighlightedToken {
  text: string;
  start: number;
  end: number;
  score: number;
  negated: boolean;
}

export interface NlpResult {
  urgency: string;
  urgency_score: number;
  confidence: number;
  highlighted_tokens: HighlightedToken[];
  rationale: string;
}

export interface EcgResult {
  superclass: "normal" | "arrhythmia" | "block" | string;
  superclass_index: number;
  confidence: number;
  probabilities: Record<string, number>;
  grad_cam: number[];
  lead_saliency: number[][];
  heart_rate_bpm?: number | null;
  backend: string;
  xai_method: string;
  rationale?: string;
}

export interface EcgSignal {
  analysis_id: string;
  leads: string[];
  fs_effective: number;
  samples: number;
  signal: number[][];
}
