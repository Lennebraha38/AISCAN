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
  const resp = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (resp.status === 401) {
    clearTokens();
    window.location.href = "/login";
    throw new Error("Oturum süresi doldu");
  }
  if (!resp.ok) {
    let detail = `${resp.status}`;
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {}
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
  getAnalysis: (id: string) =>
    request<{
      id: string;
      study_id: string;
      status: string;
      fusion_risk_score: number;
      vision_result: VisionResult | null;
      nlp_result: NlpResult | null;
      decisions: { decision: string; note: string | null; decided_at: string }[];
    }>(`/v1/analyses/${id}`),
  decide: (id: string, decision: "APPROVED" | "REJECTED", note?: string) =>
    request<Record<string, unknown>>(`/v1/analyses/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, note }),
    }),
  listAnalyses: (status?: string) =>
    request<
      { id: string; study_id: string; status: string; fusion_risk_score: number; created_at: string }[]
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
