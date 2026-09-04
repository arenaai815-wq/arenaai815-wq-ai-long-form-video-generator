"use client";
import { create } from "zustand";
import type { Clip, TimelineDocument, Track, TrackKind } from "@/types/api";
import { clamp, uid } from "@/lib/utils";

const HISTORY_LIMIT = 100;

export interface EditorState {
  projectId: string | null;
  doc: TimelineDocument | null;
  baseVersion: number | null;
  past: TimelineDocument[];
  future: TimelineDocument[];
  dirty: boolean;
  saving: boolean;
  // playback
  playhead: number;
  playing: boolean;
  // view
  zoom: number; // px per second
  selectedClipId: string | null;
  selectedTrackId: string | null;
  snap: boolean;

  load: (projectId: string, doc: TimelineDocument, version: number) => void;
  commit: (mutate: (d: TimelineDocument) => void, opts?: { transient?: boolean }) => void;
  undo: () => void;
  redo: () => void;
  markSaved: (version: number) => void;
  setSaving: (v: boolean) => void;
  setPlayhead: (t: number) => void;
  setPlaying: (v: boolean) => void;
  setZoom: (z: number) => void;
  select: (clipId: string | null, trackId?: string | null) => void;
  toggleSnap: () => void;

  // higher-level editing operations (all go through commit → undoable)
  moveClip: (trackId: string, clipId: string, start: number) => void;
  trimClip: (trackId: string, clipId: string, edge: "start" | "end", delta: number) => void;
  splitClipAt: (trackId: string, clipId: string, time: number) => void;
  deleteClip: (trackId: string, clipId: string) => void;
  duplicateClip: (trackId: string, clipId: string) => void;
  updateClip: (trackId: string, clipId: string, patch: Partial<Clip>) => void;
  reorderVideoClips: (fromIndex: number, toIndex: number) => void;
  updateTrack: (trackId: string, patch: Partial<Track>) => void;
  addTrack: (kind: TrackKind, name?: string) => string;
  addClip: (trackId: string, clip: Omit<Clip, "id">) => string;
  updateDoc: (patch: Partial<TimelineDocument>) => void;
}

function cloneDoc(d: TimelineDocument): TimelineDocument {
  return typeof structuredClone === "function" ? structuredClone(d) : (JSON.parse(JSON.stringify(d)) as TimelineDocument);
}

/** Recompute the document duration from the longest track end. */
export function docDuration(d: TimelineDocument): number {
  let end = 0;
  for (const t of d.tracks) for (const c of t.clips) end = Math.max(end, c.start + c.duration);
  return Math.round(end * 1000) / 1000;
}

/** Lay out a "video" track sequentially (clips butt against each other, overlapping by transition). */
export function ripple(track: Track): void {
  let t = 0;
  track.clips.sort((a, b) => a.start - b.start);
  for (const c of track.clips) {
    const overlap = c.transition_in && c.transition_in.type !== "none" ? Math.min(c.transition_in.duration, c.duration / 2) : 0;
    c.start = Math.max(0, t - overlap);
    t = c.start + c.duration;
  }
}

export const useEditor = create<EditorState>((set, get) => ({
  projectId: null,
  doc: null,
  baseVersion: null,
  past: [],
  future: [],
  dirty: false,
  saving: false,
  playhead: 0,
  playing: false,
  zoom: 24,
  selectedClipId: null,
  selectedTrackId: null,
  snap: true,

  load: (projectId, doc, version) => set({ projectId, doc: cloneDoc(doc), baseVersion: version, past: [], future: [], dirty: false, playhead: 0, playing: false, selectedClipId: null }),
  commit: (mutate, opts) => {
    const { doc, past } = get();
    if (!doc) return;
    const next = cloneDoc(doc);
    mutate(next);
    next.duration = docDuration(next);
    if (opts?.transient) {
      set({ doc: next, dirty: true });
      return;
    }
    set({ doc: next, past: [...past.slice(-HISTORY_LIMIT), doc], future: [], dirty: true });
  },
  undo: () => {
    const { past, doc, future } = get();
    if (!past.length || !doc) return;
    const prev = past[past.length - 1];
    set({ doc: prev, past: past.slice(0, -1), future: [doc, ...future], dirty: true });
  },
  redo: () => {
    const { past, doc, future } = get();
    if (!future.length || !doc) return;
    const [next, ...rest] = future;
    set({ doc: next, past: [...past, doc], future: rest, dirty: true });
  },
  markSaved: (version) => set({ dirty: false, baseVersion: version }),
  setSaving: (saving) => set({ saving }),
  setPlayhead: (t) => set({ playhead: clamp(t, 0, get().doc?.duration ?? 0) }),
  setPlaying: (playing) => set({ playing }),
  setZoom: (zoom) => set({ zoom: clamp(zoom, 4, 200) }),
  select: (clipId, trackId = null) => set({ selectedClipId: clipId, selectedTrackId: trackId }),
  toggleSnap: () => set({ snap: !get().snap }),

  moveClip: (trackId, clipId, start) =>
    get().commit((d) => {
      const t = d.tracks.find((x) => x.id === trackId);
      const c = t?.clips.find((x) => x.id === clipId);
      if (!t || !c) return;
      c.start = Math.max(0, start);
      if (t.kind === "video") ripple(t);
    }),
  trimClip: (trackId, clipId, edge, delta) =>
    get().commit((d) => {
      const t = d.tracks.find((x) => x.id === trackId);
      const c = t?.clips.find((x) => x.id === clipId);
      if (!t || !c) return;
      if (edge === "end") {
        c.duration = Math.max(0.5, c.duration + delta);
        if (c.asset_kind === "video" || c.asset_kind === "audio" || c.asset_kind === "voiceover") c.trim_end = Math.max(0, c.trim_end - delta);
      } else {
        const nd = Math.max(0.5, c.duration - delta);
        const applied = c.duration - nd;
        c.start = Math.max(0, c.start + applied);
        c.duration = nd;
        if (c.asset_kind === "video" || c.asset_kind === "audio" || c.asset_kind === "voiceover") c.trim_start = Math.max(0, c.trim_start + applied);
      }
      if (t.kind === "video") ripple(t);
    }),
  splitClipAt: (trackId, clipId, time) =>
    get().commit((d) => {
      const t = d.tracks.find((x) => x.id === trackId);
      const idx = t?.clips.findIndex((x) => x.id === clipId) ?? -1;
      if (!t || idx < 0) return;
      const c = t.clips[idx];
      const offset = time - c.start;
      if (offset <= 0.25 || offset >= c.duration - 0.25) return;
      const right: Clip = { ...c, id: uid("clip"), start: c.start + offset, duration: c.duration - offset, trim_start: c.trim_start + offset, transition_in: null, fade_in: 0 };
      c.duration = offset;
      c.fade_out = 0;
      t.clips.splice(idx + 1, 0, right);
    }),
  deleteClip: (trackId, clipId) =>
    get().commit((d) => {
      const t = d.tracks.find((x) => x.id === trackId);
      if (!t) return;
      t.clips = t.clips.filter((x) => x.id !== clipId);
      if (t.kind === "video") ripple(t);
    }),
  duplicateClip: (trackId, clipId) =>
    get().commit((d) => {
      const t = d.tracks.find((x) => x.id === trackId);
      const idx = t?.clips.findIndex((x) => x.id === clipId) ?? -1;
      if (!t || idx < 0) return;
      const c = t.clips[idx];
      const copy: Clip = { ...c, id: uid("clip"), start: c.start + c.duration };
      t.clips.splice(idx + 1, 0, copy);
      if (t.kind === "video") ripple(t);
    }),
  updateClip: (trackId, clipId, patch) =>
    get().commit((d) => {
      const t = d.tracks.find((x) => x.id === trackId);
      const c = t?.clips.find((x) => x.id === clipId);
      if (!t || !c) return;
      Object.assign(c, patch);
      if (t.kind === "video" && ("duration" in patch || "transition_in" in patch)) ripple(t);
    }),
  reorderVideoClips: (from, to) =>
    get().commit((d) => {
      const t = d.tracks.find((x) => x.kind === "video");
      if (!t || from === to || from < 0 || to < 0 || from >= t.clips.length || to >= t.clips.length) return;
      const [c] = t.clips.splice(from, 1);
      t.clips.splice(to, 0, c);
      // keep voiceover + text clips aligned with their scene
      ripple(t);
      const startByScene = new Map<string, number>();
      t.clips.forEach((clip) => clip.scene_id && startByScene.set(clip.scene_id, clip.start));
      for (const track of d.tracks) {
        if (track.kind === "voiceover" || track.kind === "text") {
          for (const clip of track.clips) {
            if (clip.scene_id && startByScene.has(clip.scene_id)) clip.start = startByScene.get(clip.scene_id)!;
          }
          track.clips.sort((a, b) => a.start - b.start);
        }
      }
    }),
  updateTrack: (trackId, patch) =>
    get().commit((d) => {
      const t = d.tracks.find((x) => x.id === trackId);
      if (t) Object.assign(t, patch);
    }),
  addTrack: (kind, name) => {
    const id = uid("track");
    get().commit((d) => {
      d.tracks.push({ id, kind, name: name || kind, muted: false, locked: false, volume: 1, clips: [] });
    });
    return id;
  },
  addClip: (trackId, clip) => {
    const id = uid("clip");
    get().commit((d) => {
      const t = d.tracks.find((x) => x.id === trackId);
      if (!t) return;
      t.clips.push({ ...clip, id });
      t.clips.sort((a, b) => a.start - b.start);
      if (t.kind === "video") ripple(t);
    });
    return id;
  },
  updateDoc: (patch) =>
    get().commit((d) => {
      Object.assign(d, patch);
    }),
}));

/** Which clip is under the playhead on a given track kind. */
export function clipAt(doc: TimelineDocument, kind: TrackKind, time: number): { clip: Clip; track: Track } | null {
  for (const track of doc.tracks) {
    if (track.kind !== kind || track.muted) continue;
    for (const clip of track.clips) {
      if (time >= clip.start && time < clip.start + clip.duration) return { clip, track };
    }
  }
  return null;
}
