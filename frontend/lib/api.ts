/** Backend API istemcisi. */

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Tokens {
  access_token: string;
  refresh_token: string;
  role: string;
}

export function getTokens(): Tokens | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("pulsar_tokens");
  return raw ? (JSON.parse(raw) as Tokens) : null;
}

export function setTokens(tokens: Tokens): void {
  localStorage.setItem("pulsar_tokens", JSON.stringify(tokens));
  // Middleware'in okuyabilmesi için httpOnly olmayan işaret çerezi.
  document.cookie = `pulsar_auth=1; path=/; max-age=86400; samesite=lax`;
}

export function clearTokens(): void {
  localStorage.removeItem("pulsar_tokens");
  document.cookie = "pulsar_auth=; path=/; max-age=0";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const tokens = getTokens();
  const headers = new Headers(init.headers);
  if (tokens) headers.set("Authorization", `Bearer ${tokens.access_token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let resp: Response;
  try {
    resp = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new Error(
      `Sunucuya ulaşılamıyor (${API_URL}). Bağlantıyı ve servis durumunu kontrol edin.`
    );
  }
  if (resp.status === 401 && path !== "/v1/auth/login") {
    clearTokens();
    window.location.href = "/login";
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

export const api = {
  login: (email: string, password: string) =>
    request<Tokens>("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
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
