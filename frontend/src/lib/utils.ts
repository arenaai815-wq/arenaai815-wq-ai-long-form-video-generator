import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { JobState, ProjectStatus } from "@/types/api";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(n: number | null | undefined, digits = 1): string {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  return `${(n / 1024 ** i).toFixed(i === 0 ? 0 : digits)} ${units[i]}`;
}

/** 0:00 / 1:02:03 style timecode. */
export function formatDuration(seconds: number | null | undefined, withMs = false): string {
  if (seconds == null || Number.isNaN(seconds)) return "–:––";
  const s = Math.max(0, seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const ms = Math.floor((s - Math.floor(s)) * 100);
  const core = h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
  return withMs ? `${core}.${String(ms).padStart(2, "0")}` : core;
}

export function formatMinutes(seconds: number | null | undefined): string {
  if (!seconds) return "0 min";
  const m = seconds / 60;
  return m < 1 ? `${Math.round(seconds)}s` : `${m.toFixed(m < 10 ? 1 : 0)} min`;
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 45) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} d ago`;
  return new Date(iso).toLocaleDateString();
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function formatEta(seconds: number | null | undefined): string {
  if (seconds == null) return "";
  if (seconds < 60) return `~${Math.max(1, Math.round(seconds))}s left`;
  return `~${Math.round(seconds / 60)} min left`;
}

export const JOB_STATE_LABEL: Record<JobState, string> = {
  QUEUED: "Queued",
  PROCESSING: "Processing",
  GENERATING_SCRIPT: "Writing script",
  GENERATING_AUDIO: "Generating voiceover",
  GENERATING_VISUALS: "Generating visuals",
  RENDERING: "Rendering",
  COMPLETED: "Completed",
  FAILED: "Failed",
  CANCELLED: "Cancelled",
};

export function jobStateColor(state: JobState | string): string {
  switch (state) {
    case "COMPLETED":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-300";
    case "FAILED":
      return "border-red-500/40 bg-red-500/10 text-red-300";
    case "CANCELLED":
      return "border-zinc-500/40 bg-zinc-500/10 text-zinc-300";
    case "QUEUED":
      return "border-amber-500/40 bg-amber-500/10 text-amber-300";
    default:
      return "border-brand-500/40 bg-brand-500/10 text-brand-200";
  }
}

export const PROJECT_STATUS_LABEL: Record<ProjectStatus, string> = {
  draft: "Draft",
  researching: "Researching",
  scripting: "Scripting",
  storyboarding: "Storyboarding",
  generating: "Generating",
  editing: "Editing",
  rendering: "Rendering",
  completed: "Completed",
  failed: "Failed",
  archived: "Archived",
};

export function projectStatusColor(status: ProjectStatus | string): string {
  switch (status) {
    case "completed":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-300";
    case "failed":
      return "border-red-500/40 bg-red-500/10 text-red-300";
    case "draft":
      return "border-zinc-500/40 bg-zinc-500/10 text-zinc-300";
    case "archived":
      return "border-zinc-600/40 bg-zinc-600/10 text-zinc-400";
    default:
      return "border-brand-500/40 bg-brand-500/10 text-brand-200";
  }
}

export function isTerminal(state: string | null | undefined): boolean {
  return state === "COMPLETED" || state === "FAILED" || state === "CANCELLED";
}

export function wordCount(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}

export function titleCase(s: string): string {
  return s.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function uid(prefix = "c"): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

export function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

/** Make a signed media URL usable from the browser (paths are root-relative and proxied). */
export function mediaUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  return url;
}
