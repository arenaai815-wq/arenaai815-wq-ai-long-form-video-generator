"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Image as ImageIcon, Mic2, Upload, Music4, Film, Type, Search } from "lucide-react";
import { useEditor } from "@/store/editor";
import { api, uploadFile } from "@/lib/api";
import type { MediaAsset, ProjectDetail, Scene } from "@/types/api";
import { Button, Input, Tabs } from "@/components/ui";
import { cn, formatDuration } from "@/lib/utils";

export function LeftPanel({ p, scenes }: { p: ProjectDetail; scenes: Scene[] }) {
  const [tab, setTab] = useState<"scenes" | "media" | "audio">("scenes");
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line p-2">
        <Tabs value={tab} onChange={setTab} tabs={[{ id: "scenes", label: "Scenes", count: scenes.length }, { id: "media", label: "Media" }, { id: "audio", label: "Audio" }]} />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {tab === "scenes" && <ScenesList scenes={scenes} />}
        {tab === "media" && <MediaList p={p} />}
        {tab === "audio" && <AudioList p={p} />}
      </div>
    </div>
  );
}

function ScenesList({ scenes }: { scenes: Scene[] }) {
  const { doc, select, setPlayhead, selectedClipId } = useEditor();
  const videoTrack = doc?.tracks.find((t) => t.kind === "video");
  return (
    <ul className="space-y-1">
      {scenes.map((s, i) => {
        const clip = videoTrack?.clips.find((c) => c.scene_id === s.id);
        const active = clip && clip.id === selectedClipId;
        return (
          <li key={s.id}>
            <button
              className={cn("flex w-full items-start gap-2 rounded-md border p-1.5 text-left text-xs transition", active ? "border-brand-500 bg-brand-500/10" : "border-transparent hover:bg-panel2")}
              onClick={() => {
                if (clip && videoTrack) {
                  select(clip.id, videoTrack.id);
                  setPlayhead(clip.start + 0.01);
                }
              }}
            >
              <div className="relative aspect-video w-20 shrink-0 overflow-hidden rounded bg-panel2">
                {s.visual_thumbnail_url || s.visual_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={s.visual_thumbnail_url || s.visual_url || ""} alt="" className="h-full w-full object-cover" />
                ) : (
                  <div className="grid h-full w-full place-items-center text-muted"><ImageIcon className="h-3.5 w-3.5" /></div>
                )}
                <span className="absolute left-0.5 top-0.5 rounded bg-black/60 px-1 font-mono text-[9px] text-white">{i + 1}</span>
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{s.title || `Scene ${i + 1}`}</p>
                <p className="line-clamp-2 text-[11px] text-muted">{s.narration}</p>
                <p className="mt-0.5 flex items-center gap-2 text-[10px] text-muted">
                  <span className="font-mono">{formatDuration(clip?.duration ?? s.duration_seconds)}</span>
                  <Mic2 className={cn("h-3 w-3", s.voiceover_id ? "text-emerald-300" : "opacity-40")} />
                  <ImageIcon className={cn("h-3 w-3", s.visual_asset_id ? "text-sky-300" : "opacity-40")} />
                </p>
              </div>
            </button>
          </li>
        );
      })}
      {!scenes.length && <li className="p-2 text-xs text-muted">No scenes yet. Generate the storyboard first.</li>}
    </ul>
  );
}

function MediaList({ p }: { p: ProjectDetail }) {
  const qc = useQueryClient();
  const [scope, setScope] = useState<"project" | "all">("project");
  const [q, setQ] = useState("");
  const media = useQuery({ queryKey: ["media", scope === "project" ? p.id : "all", q], queryFn: () => api.media.list({ project_id: scope === "project" ? p.id : undefined, page_size: 80, q: q || undefined }) });
  const { doc, selectedClipId, updateClip, addTrack, addClip, playhead } = useEditor();
  const upload = useMutation({
    mutationFn: (file: File) => uploadFile(file, { project_id: p.id }),
    onSuccess: () => {
      toast.success("Uploaded");
      void qc.invalidateQueries({ queryKey: ["media"] });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Upload failed"),
  });
  const sel = (() => {
    if (!doc || !selectedClipId) return null;
    for (const t of doc.tracks) {
      const c = t.clips.find((x) => x.id === selectedClipId);
      if (c) return { track: t, clip: c };
    }
    return null;
  })();
  const applyAsset = (a: MediaAsset) => {
    if (sel && (sel.track.kind === "video" || sel.track.kind === "image")) {
      updateClip(sel.track.id, sel.clip.id, { asset_id: a.id, asset_kind: a.kind === "video" ? "video" : "image", src_url: a.url, label: a.filename, trim_start: 0, trim_end: 0 });
      toast.success("Replaced clip visual (remember to save)");
      return;
    }
    // no visual selected: append a B-roll clip to an overlay track at the playhead
    const overlay = doc?.tracks.find((t) => t.kind === "image" && t.name === "B-roll") ?? null;
    const trackId = overlay?.id ?? addTrack("image", "B-roll");
    addClip(trackId, { scene_id: null, asset_id: a.id, asset_kind: a.kind === "video" ? "video" : "image", start: playhead, duration: a.duration_seconds ?? 5, trim_start: 0, trim_end: 0, volume: 1, fade_in: 0, fade_out: 0, transition_in: { type: "fade", duration: 0.4 }, effect: a.kind === "video" ? null : { type: "ken_burns", intensity: 0.1 }, text: null, label: a.filename, src_url: a.url });
    toast.success("Added to B-roll track at playhead");
  };
  return (
    <div className="space-y-2">
      <Tabs value={scope} onChange={setScope} tabs={[{ id: "project", label: "Project" }, { id: "all", label: "All" }]} />
      <div className="flex gap-1">
        <div className="relative flex-1"><Search className="pointer-events-none absolute left-2 top-2 h-3.5 w-3.5 text-muted" /><Input className="py-1.5 pl-7 text-xs" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <label className="btn-secondary cursor-pointer px-2 py-1.5 text-xs"><Upload className="h-3.5 w-3.5" /><input type="file" accept="image/*,video/*" className="hidden" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} /></label>
      </div>
      {upload.isPending && <p className="text-[11px] text-muted">Uploading…</p>}
      <p className="text-[10px] text-muted">{sel && (sel.track.kind === "video" || sel.track.kind === "image") ? "Click an asset to replace the selected clip's visual." : "Click an asset to add it as B-roll at the playhead."}</p>
      <div className="grid grid-cols-2 gap-1.5">
        {media.data?.items.filter((a) => a.source !== "render" && a.source !== "thumbnail").map((a) => (
          <button key={a.id} onClick={() => applyAsset(a)} className="group relative aspect-video overflow-hidden rounded-md border border-line hover:border-brand-500" title={a.filename}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {a.thumbnail_url || a.url ? <img src={a.thumbnail_url || a.url || ""} alt="" className="h-full w-full object-cover" /> : <div className="grid h-full w-full place-items-center bg-panel2 text-muted"><Film className="h-4 w-4" /></div>}
            <span className="absolute bottom-0.5 left-0.5 rounded bg-black/60 px-1 text-[9px] text-white">{a.kind}{a.duration_seconds ? ` · ${formatDuration(a.duration_seconds)}` : ""}</span>
          </button>
        ))}
      </div>
      {media.data && !media.data.items.length && <p className="text-xs text-muted">No media yet.</p>}
    </div>
  );
}

function AudioList({ p }: { p: ProjectDetail }) {
  const qc = useQueryClient();
  const [kind, setKind] = useState<"music" | "sfx">("music");
  const audio = useQuery({ queryKey: ["audio-library", kind], queryFn: () => api.media.audio({ kind }) });
  const { doc, addTrack, addClip, playhead } = useEditor();
  const upload = useMutation({
    mutationFn: (file: File) => uploadFile(file, { project_id: p.id, audio_kind: kind }),
    onSuccess: () => {
      toast.success("Uploaded");
      void qc.invalidateQueries({ queryKey: ["audio-library"] });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Upload failed"),
  });
  const place = (id: string, url: string | null, name: string, duration: number | null) => {
    if (!doc) return;
    const existing = doc.tracks.find((t) => t.kind === kind);
    const trackId = existing?.id ?? addTrack(kind, kind === "music" ? "Music" : "SFX");
    addClip(trackId, { scene_id: null, asset_id: id, asset_kind: "audio", start: kind === "music" ? 0 : playhead, duration: kind === "music" ? doc.duration || duration || 60 : Math.min(duration ?? 3, 30), trim_start: 0, trim_end: 0, volume: kind === "music" ? (p.settings?.music?.volume ?? 0.12) : 0.8, fade_in: kind === "music" ? 1.5 : 0, fade_out: kind === "music" ? 3 : 0.2, transition_in: null, effect: null, text: null, label: name, src_url: url });
    toast.success(kind === "music" ? "Music track set" : "SFX placed at playhead");
  };
  return (
    <div className="space-y-2">
      <Tabs value={kind} onChange={setKind} tabs={[{ id: "music", label: "Music" }, { id: "sfx", label: "SFX" }]} />
      <label className="btn-secondary w-full cursor-pointer py-1.5 text-xs"><Upload className="h-3.5 w-3.5" /> Upload {kind}<input type="file" accept="audio/*" className="hidden" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} /></label>
      <ul className="space-y-1">
        {audio.data?.map((a) => (
          <li key={a.id} className="rounded-md border border-line p-1.5 text-xs">
            <div className="flex items-center gap-2">
              <Music4 className="h-3.5 w-3.5 shrink-0 text-muted" />
              <div className="min-w-0 flex-1"><p className="truncate font-medium">{a.filename.replace(/\.[a-z0-9]+$/i, "")}</p><p className="truncate text-[10px] text-muted">{a.mood || a.tags?.join(", ") || "—"} · {formatDuration(a.duration_seconds)}</p></div>
              <Button size="sm" onClick={() => place(a.id, a.url, a.filename, a.duration_seconds)}>Use</Button>
            </div>
            {a.url && <audio src={a.url} controls preload="none" className="mt-1 h-7 w-full" />}
          </li>
        ))}
        {audio.data && !audio.data.length && <li className="text-xs text-muted">Nothing here yet.</li>}
      </ul>
      <p className="flex items-center gap-1 text-[10px] text-muted"><Type className="h-3 w-3" /> Tip: text overlays live on the Text track — select a video clip and use “Add text overlay”.</p>
    </div>
  );
}
