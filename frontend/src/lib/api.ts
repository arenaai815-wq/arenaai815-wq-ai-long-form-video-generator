/**
 * Typed API client. All requests go to the same-origin `/api/v1/*` path, which Next.js
 * proxies to the FastAPI backend (see next.config.mjs). Tokens live in memory + localStorage
 * and are refreshed transparently on 401.
 */
import type {
  ApiKeyCreated,
  ApiKeyInfo,
  AudioAsset,
  Captions,
  CheckoutResponse,
  CostEstimate,
  CreditTransaction,
  ExportInfo,
  Job,
  MediaAsset,
  Message,
  Page,
  Plan,
  ProjectCreate,
  ProjectDetail,
  ProjectStats,
  ProjectSummary,
  ProjectUpdate,
  ProviderCatalogue,
  QueueStats,
  RenderJob,
  Research,
  ResearchUpdate,
  Scene,
  SceneUpdate,
  Script,
  ScriptSection,
  ScriptStats,
  SessionInfo,
  StockSearchResult,
  StorageUsage,
  Subscription,
  Timeline,
  TimelineDocument,
  TimelineOp,
  TokenPair,
  UploadInitResponse,
  UsageRecord,
  UsageSummary,
  User,
  Voice,
  Voiceover,
  WorkerStatus,
} from "@/types/api";

export const API_BASE = "/api/v1";
const ACCESS_KEY = "lf.access";
const REFRESH_KEY = "lf.refresh";

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;
  requestId?: string;
  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}, requestId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

/* ------------------------------------------------------------ token store */
const isBrowser = typeof window !== "undefined";
let accessToken: string | null = isBrowser ? window.localStorage.getItem(ACCESS_KEY) : null;
let refreshToken: string | null = isBrowser ? window.localStorage.getItem(REFRESH_KEY) : null;
let refreshing: Promise<boolean> | null = null;

export const tokens = {
  get access() {
    return accessToken;
  },
  get refresh() {
    return refreshToken;
  },
  set(pair: TokenPair | null) {
    accessToken = pair?.access_token ?? null;
    refreshToken = pair?.refresh_token ?? null;
    if (!isBrowser) return;
    if (pair) {
      window.localStorage.setItem(ACCESS_KEY, pair.access_token);
      window.localStorage.setItem(REFRESH_KEY, pair.refresh_token);
    } else {
      window.localStorage.removeItem(ACCESS_KEY);
      window.localStorage.removeItem(REFRESH_KEY);
    }
    window.dispatchEvent(new Event("lf:auth"));
  },
};

async function tryRefresh(): Promise<boolean> {
  if (!refreshToken) return false;
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!res.ok) {
          tokens.set(null);
          return false;
        }
        tokens.set((await res.json()) as TokenPair);
        return true;
      } catch {
        return false;
      } finally {
        refreshing = null;
      }
    })();
  }
  return refreshing;
}

/* --------------------------------------------------------------- request */
interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  raw?: boolean;
  signal?: AbortSignal;
  retry?: boolean;
  headers?: Record<string, string>;
}

function qs(query?: RequestOptions["query"]): string {
  if (!query) return "";
  const p = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = path.startsWith("http") || path.startsWith("/api/") ? path : `${API_BASE}${path}`;
  const headers: Record<string, string> = { Accept: "application/json", ...(opts.headers || {}) };
  const isForm = typeof FormData !== "undefined" && opts.body instanceof FormData;
  if (opts.body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  const res = await fetch(url + qs(opts.query), {
    method: opts.method || "GET",
    headers,
    body: opts.body === undefined ? undefined : isForm ? (opts.body as FormData) : JSON.stringify(opts.body),
    signal: opts.signal,
  });

  if (res.status === 401 && opts.retry !== false && refreshToken) {
    const ok = await tryRefresh();
    if (ok) return request<T>(path, { ...opts, retry: false });
  }

  if (!res.ok) {
    let code = "http_error";
    let message = res.statusText || `Request failed (${res.status})`;
    let details: Record<string, unknown> = {};
    try {
      const data = await res.json();
      if (data?.error) {
        code = data.error.code || code;
        message = data.error.message || message;
        details = data.error.details || {};
      } else if (data?.detail) {
        message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
        code = "validation_error";
        details = { detail: data.detail };
      }
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401) tokens.set(null);
    throw new ApiError(res.status, code, message, details, res.headers.get("X-Request-ID") || undefined);
  }
  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const get = <T>(p: string, query?: RequestOptions["query"], signal?: AbortSignal) => request<T>(p, { query, signal });
const post = <T>(p: string, body?: unknown, query?: RequestOptions["query"]) => request<T>(p, { method: "POST", body, query });
const put = <T>(p: string, body?: unknown) => request<T>(p, { method: "PUT", body });
const patch = <T>(p: string, body?: unknown) => request<T>(p, { method: "PATCH", body });
const del = <T>(p: string, query?: RequestOptions["query"]) => request<T>(p, { method: "DELETE", query });

/** Build an SSE URL (EventSource cannot send headers, so the access token goes in the query). */
export function sseUrl(path: string): string {
  const u = `${API_BASE}${path}`;
  return accessToken ? `${u}${u.includes("?") ? "&" : "?"}token=${encodeURIComponent(accessToken)}` : u;
}

/* ------------------------------------------------------------------- api */
export const api = {
  auth: {
    signup: (email: string, password: string, full_name?: string) => post<TokenPair>("/auth/signup", { email, password, full_name }),
    login: (email: string, password: string) => post<TokenPair>("/auth/login", { email, password }),
    logout: () => post<Message>("/auth/logout", { refresh_token: refreshToken }),
    me: () => get<User>("/auth/me"),
    updateMe: (body: Partial<Pick<User, "full_name" | "avatar_url" | "preferences">>) => patch<User>("/auth/me", body),
    changePassword: (current_password: string, new_password: string) => post<Message>("/auth/me/password", { current_password, new_password }),
    sessions: () => get<SessionInfo[]>("/auth/sessions"),
    revokeSession: (id: string) => del<Message>(`/auth/sessions/${id}`),
    apiKeys: () => get<ApiKeyInfo[]>("/auth/api-keys"),
    createApiKey: (name: string, scopes: string[] = ["*"]) => post<ApiKeyCreated>("/auth/api-keys", { name, scopes }),
    deleteApiKey: (id: string) => del<Message>(`/auth/api-keys/${id}`),
  },
  projects: {
    list: (q?: { page?: number; page_size?: number; status?: string; q?: string; include_archived?: boolean }) => get<Page<ProjectSummary>>("/projects", q),
    stats: () => get<ProjectStats>("/projects/stats"),
    create: (body: ProjectCreate) => post<ProjectDetail>("/projects", body),
    get: (id: string) => get<ProjectDetail>(`/projects/${id}`),
    update: (id: string, body: ProjectUpdate) => patch<ProjectDetail>(`/projects/${id}`, body),
    remove: (id: string) => del<Message>(`/projects/${id}`),
    restore: (id: string) => post<ProjectDetail>(`/projects/${id}/restore`),
    duplicate: (id: string) => post<ProjectDetail>(`/projects/${id}/duplicate`),
    estimate: (id: string) => get<CostEstimate>(`/projects/${id}/estimate`),
    generate: (id: string, body?: { stages?: string[]; skip_existing?: boolean; render_preview?: boolean; options?: Record<string, Record<string, unknown>>; idempotency_key?: string }) =>
      post<Job>(`/projects/${id}/generate`, body ?? {}),
    jobs: (id: string) => get<Job[]>(`/projects/${id}/jobs`),
    export: (id: string) => get<ExportInfo>(`/projects/${id}/export`),
  },
  research: {
    get: (pid: string) => get<Research>(`/projects/${pid}/research`),
    generate: (pid: string, body?: { section_count?: number; depth?: string; focus?: string; include_sources?: boolean }) =>
      post<Job>(`/projects/${pid}/research/generate`, body ?? {}),
    update: (pid: string, body: ResearchUpdate) => put<Research>(`/projects/${pid}/research`, body),
  },
  script: {
    get: (pid: string) => get<Script>(`/projects/${pid}/script`),
    versions: (pid: string) => get<Script[]>(`/projects/${pid}/script/versions`),
    restore: (pid: string, version: number) => post<Script>(`/projects/${pid}/script/versions/${version}/restore`),
    stats: (pid: string) => get<ScriptStats>(`/projects/${pid}/script/stats`),
    generate: (pid: string, body?: { target_duration_minutes?: number; tone?: string; instructions?: string; words_per_minute?: number }) =>
      post<Job>(`/projects/${pid}/script/generate`, body ?? {}),
    update: (pid: string, body: { title?: string; hook?: string; notes?: string; words_per_minute?: number }) => patch<Script>(`/projects/${pid}/script`, body),
    addSection: (pid: string, body: { heading: string; content?: string; kind?: string; after_section_id?: string | null; talking_points?: string[] }) =>
      post<Script>(`/projects/${pid}/script/sections`, body),
    updateSection: (pid: string, sid: string, body: Partial<Pick<ScriptSection, "heading" | "content" | "kind" | "talking_points" | "is_locked">>) =>
      patch<Script>(`/projects/${pid}/script/sections/${sid}`, body),
    deleteSection: (pid: string, sid: string) => del<Script>(`/projects/${pid}/script/sections/${sid}`),
    reorder: (pid: string, section_ids: string[]) => post<Script>(`/projects/${pid}/script/sections/reorder`, { section_ids }),
    regenerateSection: (pid: string, sid: string, body?: { instructions?: string; target_words?: number; tone?: string }) =>
      post<Job>(`/projects/${pid}/script/sections/${sid}/regenerate`, body ?? {}),
    lockSection: (pid: string, sid: string, locked: boolean) => post<Message>(`/projects/${pid}/script/sections/${sid}/lock`, undefined, { locked }),
  },
  scenes: {
    list: (pid: string) => get<Scene[]>(`/projects/${pid}/scenes`),
    generate: (pid: string, body?: { scene_target_seconds?: number; regenerate_prompts_only?: boolean }) => post<Job>(`/projects/${pid}/scenes/generate`, body ?? {}),
    generateVisuals: (pid: string, body?: { scene_ids?: string[]; force?: boolean; visual_type?: string; provider?: string; prompt_override?: string }) =>
      post<Job>(`/projects/${pid}/scenes/visuals/generate`, body ?? {}),
    create: (pid: string, body: { narration?: string; title?: string; after_scene_id?: string | null; visual_type?: string; image_prompt?: string; duration_seconds?: number }) =>
      post<Scene[]>(`/projects/${pid}/scenes`, body),
    reorder: (pid: string, scene_ids: string[]) => post<Scene[]>(`/projects/${pid}/scenes/reorder`, { scene_ids }),
    get: (pid: string, sid: string) => get<Scene>(`/projects/${pid}/scenes/${sid}`),
    update: (pid: string, sid: string, body: SceneUpdate) => patch<Scene>(`/projects/${pid}/scenes/${sid}`, body),
    remove: (pid: string, sid: string) => del<Scene[]>(`/projects/${pid}/scenes/${sid}`),
    split: (pid: string, sid: string, at_character: number) => post<Scene[]>(`/projects/${pid}/scenes/${sid}/split`, { at_character }),
    visualFromAsset: (pid: string, sid: string, asset_id: string) => post<Scene>(`/projects/${pid}/scenes/${sid}/visual/from-asset`, { asset_id }),
    visualFromStock: (pid: string, sid: string, item: StockSearchResult) =>
      post<Scene>(`/projects/${pid}/scenes/${sid}/visual/from-stock`, {
        item_id: item.id,
        kind: item.kind,
        download_url: item.download_url,
        width: item.width,
        height: item.height,
        duration_seconds: item.duration_seconds,
        source: item.source,
      }),
    clearVisual: (pid: string, sid: string) => del<Message>(`/projects/${pid}/scenes/${sid}/visual`),
  },
  voiceovers: {
    voices: (q?: { language?: string; provider?: string }) => get<Voice[]>("/voices", q),
    previewUrl: () => `${API_BASE}/voices/preview`,
    preview: async (body: { text?: string; voice_id: string; provider?: string; language?: string }) => {
      const res = await request<Response>("/voices/preview", { method: "POST", body, raw: true });
      return await res.blob();
    },
    list: (pid: string) => get<Voiceover[]>(`/projects/${pid}/voiceovers`),
    generate: (pid: string, body?: { scene_ids?: string[]; force?: boolean; voice_id?: string; provider?: string; language?: string; style?: string; speed?: number }) =>
      post<Job>(`/projects/${pid}/voiceovers/generate`, body ?? {}),
    remove: (pid: string, vid: string) => del<Message>(`/projects/${pid}/voiceovers/${vid}`),
  },
  captions: {
    get: (pid: string) => get<Captions>(`/projects/${pid}/captions`),
    generate: (pid: string, body?: { mode?: string; language?: string; style?: Partial<Captions["style"]>; max_chars_per_line?: number; max_lines?: number }) =>
      post<Job>(`/projects/${pid}/captions/generate`, body ?? {}),
    update: (pid: string, body: { cues?: Captions["cues"]; style?: Partial<Captions["style"]>; language?: string }) => put<Captions>(`/projects/${pid}/captions`, body),
    exportUrl: (pid: string, fmt: "srt" | "vtt") => `${API_BASE}/projects/${pid}/captions/export.${fmt}`,
  },
  timeline: {
    get: (pid: string) => get<Timeline>(`/projects/${pid}/timeline`),
    save: (pid: string, data: TimelineDocument, base_version?: number) => put<Timeline>(`/projects/${pid}/timeline`, { data, base_version }),
    op: (pid: string, op: TimelineOp, payload: Record<string, unknown>) => post<Timeline>(`/projects/${pid}/timeline/ops`, { op, payload }),
    sync: (pid: string) => post<Timeline>(`/projects/${pid}/timeline/sync`),
  },
  render: {
    start: (pid: string, body: { preview?: boolean; resolution?: string; fps?: number; burn_captions?: boolean; include_watermark?: boolean; idempotency_key?: string; range_start?: number; range_end?: number }) =>
      post<RenderJob>(`/projects/${pid}/render`, body),
    list: (pid: string) => get<RenderJob[]>(`/projects/${pid}/renders`),
    get: (pid: string, rid: string) => get<RenderJob>(`/projects/${pid}/renders/${rid}`),
  },
  jobs: {
    list: (q?: { page?: number; page_size?: number; state?: string; project_id?: string; active?: boolean }) => get<Page<Job | RenderJob>>("/jobs", q),
    get: (id: string) => get<Job | RenderJob>(`/jobs/${id}`),
    logs: (id: string) => get<{ job_id: string; logs: Job["logs"]; error: string | null; error_details: Record<string, unknown> | null }>(`/jobs/${id}/logs`),
    cancel: (id: string) => post<Message>(`/jobs/${id}/cancel`),
    retry: (id: string) => post<Job | RenderJob>(`/jobs/${id}/retry`),
  },
  media: {
    list: (q?: { page?: number; page_size?: number; project_id?: string; kind?: string; source?: string; q?: string; reusable_only?: boolean }) => get<Page<MediaAsset>>("/media", q),
    storage: () => get<StorageUsage>("/media/storage"),
    audio: (q?: { kind?: string; project_id?: string; mood?: string }) => get<AudioAsset[]>("/media/audio", q),
    deleteAudio: (id: string) => del<Message>(`/media/audio/${id}`),
    get: (id: string) => get<MediaAsset>(`/media/${id}`),
    update: (id: string, body: { filename?: string; tags?: string[]; is_reusable?: boolean; project_id?: string | null }) => patch<MediaAsset>(`/media/${id}`, body),
    remove: (id: string) => del<Message>(`/media/${id}`),
    uploadInit: (body: { filename: string; content_type: string; size_bytes: number; project_id?: string | null; kind?: string; audio_kind?: string }) =>
      post<UploadInitResponse>("/media/uploads/init", body),
    uploadComplete: (body: { storage_key: string; filename: string; content_type: string; project_id?: string | null; kind?: string; audio_kind?: string; tags?: string[]; is_reusable?: boolean }) =>
      post<MediaAsset | AudioAsset>("/media/uploads/complete", body),
    upload: (file: File, extra: { project_id?: string; kind?: string; audio_kind?: string; tags?: string } = {}) => {
      const fd = new FormData();
      fd.append("file", file);
      Object.entries(extra).forEach(([k, v]) => v !== undefined && fd.append(k, String(v)));
      return request<MediaAsset | AudioAsset>("/media/upload", { method: "POST", body: fd });
    },
    stockSearch: (q: { q: string; kind?: string; page?: number; per_page?: number; orientation?: string; provider?: string }) => get<StockSearchResult[]>("/media/stock/search", q),
    stockImport: (item: StockSearchResult, project_id?: string, scene_id?: string) => post<MediaAsset>("/media/stock/import", { item, project_id, scene_id }),
  },
  usage: {
    summary: (period?: string) => get<UsageSummary>("/usage/summary", { period }),
    records: (q?: { page?: number; page_size?: number; kind?: string; project_id?: string }) => get<Page<UsageRecord>>("/usage/records", q),
    credits: (q?: { page?: number; page_size?: number }) => get<Page<CreditTransaction>>("/usage/credits", q),
    projects: (period?: string) => get<{ project_id: string | null; title: string | null; credits: number; records: number }[]>("/usage/projects", { period }),
  },
  billing: {
    plans: () => get<Plan[]>("/billing/plans"),
    subscription: () => get<Subscription>("/billing/subscription"),
    changePlan: (plan: string) => post<Subscription>("/billing/subscription/change", { plan }),
    cancel: () => post<Subscription>("/billing/subscription/cancel"),
    checkout: (plan: string, success_url?: string, cancel_url?: string) => post<CheckoutResponse>("/billing/checkout", { plan, success_url, cancel_url }),
    buyCredits: (credits: number) => post<CheckoutResponse>("/billing/credits/purchase", { credits }),
    portal: () => get<Message>("/billing/portal"),
  },
  providers: {
    list: () => get<ProviderCatalogue>("/providers"),
    models: (kind: string) => get<{ kind: string; provider: string; models: unknown[] }>(`/providers/${kind}/models`),
  },
  health: {
    api: () => get<{ status: string; version?: string; checks?: Record<string, unknown> }>("/health"),
    workers: () => get<WorkerStatus[]>("/health/workers"),
    queues: () => get<QueueStats>("/health/queues"),
  },
};

/** Upload a file directly to storage using a presigned URL, falling back to the API multipart route. */
export async function uploadFile(
  file: File,
  opts: { project_id?: string; kind?: string; audio_kind?: string; onProgress?: (pct: number) => void } = {},
): Promise<MediaAsset | AudioAsset> {
  const init = await api.media.uploadInit({
    filename: file.name,
    content_type: file.type || "application/octet-stream",
    size_bytes: file.size,
    project_id: opts.project_id,
    kind: opts.kind,
    audio_kind: opts.audio_kind,
  });
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(init.method || "PUT", init.upload_url);
    Object.entries(init.headers || {}).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    if (!init.headers || !init.headers["Content-Type"]) xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    xhr.upload.onprogress = (e) => e.lengthComputable && opts.onProgress?.(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`Upload failed (${xhr.status})`)));
    xhr.onerror = () => reject(new Error("Upload failed"));
    xhr.send(file);
  });
  return api.media.uploadComplete({
    storage_key: init.storage_key,
    filename: file.name,
    content_type: file.type || "application/octet-stream",
    project_id: opts.project_id,
    kind: opts.kind,
    audio_kind: opts.audio_kind,
  });
}
