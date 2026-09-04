/**
 * TypeScript mirrors of the backend Pydantic schemas (backend/app/schemas/*).
 * Keep these in sync with the API — they are the contract the UI is built against.
 */

export type UUID = string;

export type JobState =
  | "QUEUED"
  | "PROCESSING"
  | "GENERATING_SCRIPT"
  | "GENERATING_AUDIO"
  | "GENERATING_VISUALS"
  | "RENDERING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export const TERMINAL_STATES: JobState[] = ["COMPLETED", "FAILED", "CANCELLED"];

export type JobType =
  | "full_pipeline"
  | "research"
  | "script"
  | "script_section"
  | "scenes"
  | "voiceover"
  | "visuals"
  | "captions"
  | "render"
  | "render_preview"
  | string;

export type ProjectStatus =
  | "draft"
  | "researching"
  | "scripting"
  | "storyboarding"
  | "generating"
  | "editing"
  | "rendering"
  | "completed"
  | "failed"
  | "archived";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages?: number;
}

export interface Message {
  message: string;
}

/* ------------------------------------------------------------------ auth */
export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface User {
  id: UUID;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  is_verified: boolean;
  credits_balance: number;
  storage_bytes_used: number;
  preferences: Record<string, unknown>;
  created_at: string;
  last_login_at: string | null;
}

export interface SessionInfo {
  id: UUID;
  user_agent: string | null;
  ip_address: string | null;
  created_at: string;
  last_used_at: string | null;
  expires_at: string;
  is_current: boolean;
}

export interface ApiKeyInfo {
  id: UUID;
  name: string;
  key_prefix: string;
  scopes: string[];
  last_used_at: string | null;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
}

export interface ApiKeyCreated extends ApiKeyInfo {
  key: string;
}

/* -------------------------------------------------------------- projects */
export interface VoiceSettings {
  provider: string | null;
  voice_id: string;
  voice_name: string | null;
  language: string;
  style: string | null;
  speed: number;
}

export interface CaptionStyleSettings {
  enabled: boolean;
  burn_in: boolean;
  font_family: string;
  font_size: number;
  color: string;
  outline_color: string;
  outline_width: number;
  background_color: string | null;
  position: "top" | "center" | "bottom";
  margin_v: number;
  animation: "none" | "fade" | "pop" | "karaoke";
  max_chars_per_line: number;
  max_lines: number;
  timing_offset: number;
  highlight_color: string;
}

export interface MusicSettings {
  enabled: boolean;
  asset_id: UUID | null;
  mood: string | null;
  volume: number;
  ducking: boolean;
  fade_in: number;
  fade_out: number;
}

export interface ProjectSettings {
  voice: VoiceSettings;
  captions: CaptionStyleSettings;
  music: MusicSettings;
  visuals: {
    mode: "ai_image" | "ai_video" | "stock" | "mixed";
    ai_video_ratio: number;
    motion: string;
    transition: string;
    transition_duration: number;
    image_provider: string | null;
    video_provider: string | null;
    [k: string]: unknown;
  };
  intro: { enabled: boolean; duration: number; title: string | null; subtitle: string | null };
  outro: { enabled: boolean; duration: number; text: string | null; cta: string | null };
  watermark: { enabled: boolean; text: string | null; asset_id: UUID | null; position: string; opacity: number };
  words_per_minute: number;
  scene_target_seconds: number;
}

export interface ProjectSummary {
  id: UUID;
  title: string;
  topic: string;
  niche: string | null;
  language: string;
  tone: string;
  video_format: string;
  target_duration_minutes: number;
  aspect_ratio: string;
  resolution: string;
  visual_style: string;
  status: ProjectStatus;
  thumbnail_url: string | null;
  final_video_url: string | null;
  estimated_duration_seconds: number | null;
  created_at: string;
  updated_at: string;
  active_job: Partial<Job> | null;
}

export interface ProjectDetail extends ProjectSummary {
  description: string | null;
  target_audience: string | null;
  settings: ProjectSettings;
  thumbnail_asset_id: UUID | null;
  final_video_asset_id: UUID | null;
  last_opened_at: string | null;
  counts: Record<string, number>;
  pipeline: Record<string, boolean>;
}

export interface ProjectCreate {
  title: string;
  topic: string;
  description?: string | null;
  niche?: string | null;
  target_audience?: string | null;
  language: string;
  tone: string;
  video_format: string;
  target_duration_minutes: number;
  aspect_ratio: string;
  resolution: string;
  visual_style: string;
  settings?: Partial<ProjectSettings> | null;
}

export type ProjectUpdate = Partial<Omit<ProjectCreate, "settings">> & {
  status?: ProjectStatus;
  settings?: Record<string, unknown>;
};

export interface ProjectStats {
  total: number;
  drafts: number;
  generating: number;
  completed: number;
  failed: number;
}

export interface CostEstimate {
  credits: number;
  breakdown: Record<string, number>;
  balance: number;
  sufficient: boolean;
}

/* ------------------------------------------------------------------ jobs */
export interface JobLogEntry {
  ts: string;
  level: "info" | "warning" | "error" | string;
  message: string;
}

export interface Job {
  id: UUID;
  project_id: UUID;
  job_type: JobType;
  state: JobState;
  progress: number;
  stage: string | null;
  message: string | null;
  attempt: number;
  max_attempts: number;
  cancel_requested: boolean;
  params: Record<string, unknown>;
  result: Record<string, unknown>;
  error: string | null;
  eta_seconds: number | null;
  credits_reserved: number;
  credits_charged: number;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
  kind: "generation" | "render";
  logs: JobLogEntry[];
}

export interface RenderJob extends Job {
  is_preview: boolean;
  width: number;
  height: number;
  fps: number;
  burn_captions: boolean;
  include_watermark: boolean;
  timeline_version: number | null;
  output_url: string | null;
  output_size_bytes: number | null;
  output_duration_seconds: number | null;
  render_seconds: number | null;
  thumbnail_url?: string | null;
}

export interface ProgressEvent {
  job_id: string;
  project_id: string;
  job_type: string;
  state: JobState;
  stage: string;
  progress: number;
  message: string;
  eta_seconds: number | null;
  result: Record<string, unknown> | null;
  error: string | null;
  ts: string;
}

/* -------------------------------------------------------------- research */
export interface ResearchStatistic {
  value: string;
  context: string;
  source?: string | null;
}
export interface ResearchSource {
  title: string;
  url?: string | null;
  note?: string | null;
}
export interface ResearchSection {
  title: string;
  key_points: string[];
  facts: string[];
  statistics: ResearchStatistic[];
  sources: ResearchSource[];
  narrative_hooks: string[];
}
export interface Research {
  id: UUID;
  project_id: UUID;
  summary: string | null;
  sections: ResearchSection[];
  key_facts: string[];
  statistics: ResearchStatistic[];
  sources: ResearchSource[];
  suggested_angles: string[];
  keywords: string[];
  provider: string | null;
  model: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}
export interface ResearchUpdate {
  summary?: string | null;
  sections?: ResearchSection[];
  key_facts?: string[];
  statistics?: ResearchStatistic[];
  sources?: ResearchSource[];
  suggested_angles?: string[];
  keywords?: string[];
  approved?: boolean;
}

/* ---------------------------------------------------------------- script */
export type SectionKind = "hook" | "intro" | "body" | "story" | "transition" | "conclusion" | "cta" | string;

export interface ScriptSection {
  id: UUID;
  script_id: UUID;
  order_index: number;
  kind: SectionKind;
  heading: string;
  content: string;
  summary: string | null;
  talking_points: string[];
  word_count: number;
  estimated_duration_seconds: number;
  is_locked: boolean;
  regeneration_count: number;
  updated_at: string;
}

export interface Script {
  id: UUID;
  project_id: UUID;
  version: number;
  is_current: boolean;
  title: string | null;
  hook: string | null;
  outline: unknown[];
  word_count: number;
  estimated_duration_seconds: number;
  target_duration_minutes: number;
  words_per_minute: number;
  provider: string | null;
  model: string | null;
  notes: string | null;
  sections: ScriptSection[];
  created_at: string;
  updated_at: string;
}

export interface ScriptStats {
  word_count: number;
  estimated_duration_seconds: number;
  target_duration_seconds: number;
  sections: number;
  words_per_minute: number;
  delta_seconds: number;
}

/* ---------------------------------------------------------------- scenes */
export type VisualType = "ai_image" | "ai_video" | "stock_video" | "stock_image" | "upload" | "text_card" | string;

export interface Scene {
  id: UUID;
  project_id: UUID;
  section_id: UUID | null;
  order_index: number;
  title: string | null;
  narration: string;
  visual_description: string | null;
  suggested_footage: string | null;
  image_prompt: string | null;
  video_prompt: string | null;
  negative_prompt: string | null;
  on_screen_text: string | null;
  visual_type: VisualType;
  duration_seconds: number;
  transition: string;
  transition_duration: number;
  motion_effect: string;
  music_suggestion: string | null;
  music_mood: string | null;
  sound_effects: string[];
  keywords: string[];
  visual_asset_id: UUID | null;
  voiceover_id: UUID | null;
  status: string;
  extra: Record<string, unknown>;
  updated_at: string;
  visual_url: string | null;
  visual_thumbnail_url: string | null;
  visual_kind: string | null;
  voiceover_url: string | null;
  voiceover_duration: number | null;
  voiceover_status: string | null;
  start_time: number | null;
}

export type SceneUpdate = Partial<
  Pick<
    Scene,
    | "title"
    | "narration"
    | "visual_description"
    | "suggested_footage"
    | "image_prompt"
    | "video_prompt"
    | "negative_prompt"
    | "on_screen_text"
    | "visual_type"
    | "duration_seconds"
    | "transition"
    | "transition_duration"
    | "motion_effect"
    | "music_suggestion"
    | "music_mood"
    | "sound_effects"
    | "keywords"
    | "visual_asset_id"
    | "extra"
  >
>;

/* ------------------------------------------------------------- voiceover */
export interface Voice {
  id: string;
  name: string;
  language: string;
  gender: string | null;
  accent: string | null;
  styles: string[];
  preview_url: string | null;
  provider: string;
  is_premium: boolean;
}

export interface Voiceover {
  id: UUID;
  project_id: UUID;
  scene_id: UUID | null;
  text: string;
  provider: string;
  voice_id: string;
  voice_name: string | null;
  language: string;
  style: string | null;
  speed: number;
  content_type: string;
  size_bytes: number;
  duration_seconds: number | null;
  word_timings: { word: string; start: number; end: number }[];
  status: string;
  url: string | null;
  created_at: string;
}

/* -------------------------------------------------------------- captions */
export interface CaptionWord {
  word: string;
  start: number;
  end: number;
}
export interface CaptionCue {
  index: number;
  start: number;
  end: number;
  text: string;
  scene_id?: string | null;
  words?: CaptionWord[];
}
export interface Captions {
  id: UUID;
  project_id: UUID;
  language: string;
  cues: CaptionCue[];
  style: CaptionStyleSettings;
  source: string;
  provider: string | null;
  is_current: boolean;
  cue_count: number;
  created_at: string;
  updated_at: string;
  srt_url: string | null;
  vtt_url: string | null;
}

/* -------------------------------------------------------------- timeline */
export type TrackKind = "video" | "image" | "audio" | "music" | "sfx" | "voiceover" | "captions" | "text";
export type TransitionType =
  | "none"
  | "fade"
  | "fadeblack"
  | "fadewhite"
  | "dissolve"
  | "wipeleft"
  | "wiperight"
  | "slideleft"
  | "slideright"
  | "smoothleft"
  | "smoothright"
  | "circleopen"
  | "circleclose"
  | "radial"
  | "pixelize"
  | string;
export type MotionType = "none" | "ken_burns" | "zoom_in" | "zoom_out" | "pan_left" | "pan_right" | "pan_up" | "pan_down" | string;
export type TextPosition = "top" | "center" | "bottom" | "top_left" | "top_right" | "bottom_left" | "bottom_right" | string;

export interface Transition {
  type: TransitionType;
  duration: number;
}
export interface MotionEffect {
  type: MotionType;
  intensity: number;
}
export interface TextOverlay {
  content: string;
  font_family: string;
  font_size: number;
  color: string;
  background: string | null;
  position: TextPosition;
  animation: "none" | "fade" | "slide_up" | "typewriter";
}
export interface Clip {
  id: string;
  scene_id: string | null;
  asset_id: string | null;
  asset_kind: "image" | "video" | "audio" | "voiceover" | "text" | null;
  start: number;
  duration: number;
  trim_start: number;
  trim_end: number;
  volume: number;
  fade_in: number;
  fade_out: number;
  transition_in: Transition | null;
  effect: MotionEffect | null;
  text: TextOverlay | null;
  label: string | null;
  src_url: string | null;
}
export interface Track {
  id: string;
  kind: TrackKind;
  name: string;
  muted: boolean;
  locked: boolean;
  volume: number;
  clips: Clip[];
}
export interface WatermarkDoc {
  enabled: boolean;
  asset_id: string | null;
  text: string | null;
  position: "top_left" | "top_right" | "bottom_left" | "bottom_right";
  opacity: number;
}
export interface TimelineDocument {
  version: number;
  fps: number;
  width: number;
  height: number;
  duration: number;
  background_color: string;
  tracks: Track[];
  captions: CaptionStyleSettings;
  watermark: WatermarkDoc;
}
export interface Timeline {
  id: UUID;
  project_id: UUID;
  version: number;
  fps: number;
  width: number;
  height: number;
  duration_seconds: number;
  data: TimelineDocument;
  created_at: string;
  updated_at: string;
}
export type TimelineOp =
  | "reorder_scenes"
  | "trim_clip"
  | "split_clip"
  | "set_volume"
  | "set_fade"
  | "move_clip"
  | "delete_clip"
  | "set_transition"
  | "set_effect";

/* ----------------------------------------------------------------- media */
export type MediaKind = "image" | "video" | string;
export type MediaSource = "ai_image" | "ai_video" | "stock" | "upload" | "render" | "thumbnail" | "system" | string;

export interface MediaAsset {
  id: UUID;
  project_id: UUID | null;
  scene_id: UUID | null;
  kind: MediaKind;
  source: MediaSource;
  filename: string;
  content_type: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  fps: number | null;
  prompt: string | null;
  provider: string | null;
  tags: string[];
  is_reusable: boolean;
  is_uploaded: boolean;
  created_at: string;
  url: string | null;
  thumbnail_url: string | null;
}

export interface AudioAsset {
  id: UUID;
  project_id: UUID | null;
  kind: "music" | "sfx" | "voiceover" | string;
  source: MediaSource;
  filename: string;
  content_type: string;
  size_bytes: number;
  duration_seconds: number | null;
  mood: string | null;
  bpm: number | null;
  license: string | null;
  tags: string[];
  is_system: boolean;
  created_at: string;
  url: string | null;
}

export interface StockSearchResult {
  id: string;
  kind: string;
  url: string;
  download_url: string;
  thumbnail_url: string | null;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  author: string | null;
  source: string;
  license: string;
}

export interface StorageUsage {
  used_bytes: number;
  limit_bytes: number;
  by_kind: Record<string, number>;
  asset_count: number;
}

export interface UploadInitResponse {
  upload_url: string;
  storage_key: string;
  method: string;
  headers: Record<string, string>;
  expires_in: number;
}

/* --------------------------------------------------------------- billing */
export interface UsageSummary {
  period: string;
  credits_balance: number;
  credits_used: number;
  credits_granted: number;
  by_kind: Record<string, { quantity: number; credits: number; unit: string }>;
  storage_used_bytes: number;
  storage_limit_bytes: number;
  render_minutes: number;
  videos_completed: number;
  daily: { day: string; credits: number }[];
}

export interface CreditTransaction {
  id: UUID;
  kind: string;
  amount: number;
  balance_after: number;
  description: string | null;
  project_id: UUID | null;
  job_id: UUID | null;
  reference: string | null;
  created_at: string;
}

export interface UsageRecord {
  id: UUID;
  project_id: UUID | null;
  job_id: UUID | null;
  kind: string;
  quantity: number;
  unit: string;
  credits: number;
  provider: string | null;
  model: string | null;
  period: string;
  created_at: string;
}

export interface Plan {
  id: string;
  name: string;
  price_usd_month: number;
  monthly_credits: number;
  storage_gb: number;
  max_video_minutes: number;
  max_resolution: string;
  watermark: boolean;
  concurrent_renders: number;
  features: string[];
  is_current: boolean;
}

export interface Subscription {
  id: UUID;
  plan: string;
  status: string;
  monthly_credits: number;
  storage_limit_bytes: number;
  max_video_minutes: number;
  max_resolution: string;
  watermark_required: boolean;
  concurrent_renders: number;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  payment_provider: string | null;
}

export interface CheckoutResponse {
  checkout_url: string | null;
  mode: "stripe" | "manual";
  message: string;
}

/* ------------------------------------------------------------- providers */
export interface ProviderInfo {
  name: string;
  display_name: string;
  kind: string;
  is_mock: boolean;
  is_configured: boolean;
  default_model: string | null;
  capabilities: Record<string, unknown>;
}

export interface ProviderCatalogue {
  active: Record<string, string>;
  available: Record<string, ProviderInfo[]>;
  configured_from: Record<string, string>;
}

export interface WorkerStatus {
  worker_id: string;
  hostname: string;
  queues: string[];
  concurrency: number;
  active_tasks: number;
  processed_total: number;
  failed_total: number;
  last_heartbeat_at: string;
  healthy: boolean;
  version: string | null;
}

export interface QueueStats {
  queued: number;
  processing: number;
  completed_24h: number;
  failed_24h: number;
  workers_online: number;
  queue_depths: Record<string, number>;
}

export interface ExportInfo {
  asset_id: UUID;
  filename: string;
  size_bytes: number;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  url: string;
  thumbnail_url: string | null;
}
