"use client";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Wand2, Mic2, RefreshCw, Type, Music4, Captions as CaptionsIcon, Sparkles, Image as ImageIcon, Download } from "lucide-react";
import { useEditor } from "@/store/editor";
import { api, ApiError } from "@/lib/api";
import type { Captions, Clip, ProjectDetail, Scene, Track, CaptionStyleSettings, TextOverlay } from "@/types/api";
import { Alert, Button, Field, Input, Select, Slider, Tabs, Textarea, Toggle } from "@/components/ui";
import { formatDuration } from "@/lib/utils";

const TRANSITIONS = ["none", "fade", "fadeblack", "fadewhite", "dissolve", "wipeleft", "wiperight", "slideleft", "slideright", "smoothleft", "smoothright", "circleopen", "circleclose", "radial", "pixelize"];
const MOTIONS = ["none", "ken_burns", "zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"];
const POSITIONS = ["center", "top", "bottom", "top_left", "top_right", "bottom_left", "bottom_right"];

export function Inspector({ p, scenes, captions }: { p: ProjectDetail; scenes: Scene[]; captions: Captions | null }) {
  const { doc, selectedClipId } = useEditor();
  const [tab, setTab] = useState<"clip" | "ai" | "captions" | "audio">("clip");
  const sel = useMemo(() => {
    if (!doc || !selectedClipId) return null;
    for (const t of doc.tracks) {
      const c = t.clips.find((x) => x.id === selectedClipId);
      if (c) return { track: t, clip: c };
    }
    return null;
  }, [doc, selectedClipId]);
  const scene = sel?.clip.scene_id ? scenes.find((s) => s.id === sel.clip.scene_id) ?? null : null;

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line p-2">
        <Tabs value={tab} onChange={setTab} tabs={[{ id: "clip", label: "Clip" }, { id: "ai", label: "AI" }, { id: "captions", label: "Captions" }, { id: "audio", label: "Audio" }]} />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {tab === "clip" && (sel ? <ClipPanel track={sel.track} clip={sel.clip} scene={scene} /> : <p className="text-xs text-muted">Select a clip on the timeline to edit its properties. Double-click a clip to jump to it.</p>)}
        {tab === "ai" && <AIPanel p={p} scene={scene} clip={sel?.clip ?? null} />}
        {tab === "captions" && <CaptionsPanel p={p} captions={captions} />}
        {tab === "audio" && <AudioPanel p={p} />}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ clip */
function ClipPanel({ track, clip, scene }: { track: Track; clip: Clip; scene: Scene | null }) {
  const updateClip = useEditor((s) => s.updateClip);
  const up = (patch: Partial<Clip>) => updateClip(track.id, clip.id, patch);
  const isVisual = track.kind === "video" || track.kind === "image";
  const isAudio = ["voiceover", "music", "sfx", "audio"].includes(track.kind);
  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm font-semibold">{clip.label || clip.text?.content || track.name}</p>
        <p className="text-xs text-muted">{track.kind} · {formatDuration(clip.start)} → {formatDuration(clip.start + clip.duration)} {scene && `· scene ${scene.order_index + 1}`}</p>
      </div>
      <Field label="Label"><Input value={clip.label ?? ""} onChange={(e) => up({ label: e.target.value })} /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Start (s)"><Input type="number" step={0.1} min={0} value={Number(clip.start.toFixed(2))} disabled={track.kind === "video"} onChange={(e) => up({ start: Math.max(0, Number(e.target.value)) })} /></Field>
        <Field label="Duration (s)"><Input type="number" step={0.1} min={0.5} value={Number(clip.duration.toFixed(2))} onChange={(e) => up({ duration: Math.max(0.5, Number(e.target.value)) })} /></Field>
      </div>
      {(clip.asset_kind === "video" || isAudio) && (
        <div className="grid grid-cols-2 gap-3">
          <Field label="Trim in (s)"><Input type="number" step={0.1} min={0} value={Number(clip.trim_start.toFixed(2))} onChange={(e) => up({ trim_start: Math.max(0, Number(e.target.value)) })} /></Field>
          <Field label="Trim out (s)"><Input type="number" step={0.1} min={0} value={Number(clip.trim_end.toFixed(2))} onChange={(e) => up({ trim_end: Math.max(0, Number(e.target.value)) })} /></Field>
        </div>
      )}
      {isVisual && (
        <>
          <Field label="Transition in">
            <div className="flex gap-2">
              <Select value={clip.transition_in?.type ?? "none"} onChange={(e) => up({ transition_in: e.target.value === "none" ? null : { type: e.target.value, duration: clip.transition_in?.duration ?? 0.6 } })}>{TRANSITIONS.map((t) => <option key={t}>{t}</option>)}</Select>
              <Input className="w-20" type="number" step={0.1} min={0} max={3} value={clip.transition_in?.duration ?? 0} disabled={!clip.transition_in} onChange={(e) => up({ transition_in: { type: clip.transition_in?.type ?? "fade", duration: Number(e.target.value) } })} />
            </div>
          </Field>
          <Field label={`Motion · ${clip.effect?.type ?? "none"}`}>
            <Select value={clip.effect?.type ?? "none"} onChange={(e) => up({ effect: e.target.value === "none" ? null : { type: e.target.value, intensity: clip.effect?.intensity ?? 0.1 } })}>{MOTIONS.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</Select>
          </Field>
          {clip.effect && (
            <Field label={`Zoom/pan intensity · ${Math.round((clip.effect.intensity ?? 0.1) * 100)}%`}>
              <Slider min={0.02} max={0.5} step={0.01} value={clip.effect.intensity ?? 0.1} onChange={(v) => up({ effect: { type: clip.effect!.type, intensity: v } })} />
            </Field>
          )}
        </>
      )}
      {(isAudio || clip.asset_kind === "video") && (
        <>
          <Field label={`Volume · ${Math.round(clip.volume * 100)}%`}><Slider min={0} max={2} step={0.01} value={clip.volume} onChange={(v) => up({ volume: v })} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={`Fade in · ${clip.fade_in.toFixed(1)}s`}><Slider min={0} max={5} step={0.1} value={clip.fade_in} onChange={(v) => up({ fade_in: v })} /></Field>
            <Field label={`Fade out · ${clip.fade_out.toFixed(1)}s`}><Slider min={0} max={5} step={0.1} value={clip.fade_out} onChange={(v) => up({ fade_out: v })} /></Field>
          </div>
        </>
      )}
      {(track.kind === "text" || clip.text) && <TextEditor text={clip.text ?? defaultText()} onChange={(t) => up({ text: t })} />}
      {isVisual && !clip.text && (
        <Button size="sm" variant="ghost" onClick={() => up({ text: defaultText(clip.label ?? "") })}><Type className="h-3.5 w-3.5" /> Add text overlay on this clip</Button>
      )}
    </div>
  );
}

function defaultText(content = "Headline"): TextOverlay {
  return { content, font_family: "DejaVu Sans", font_size: 56, color: "#FFFFFF", background: null, position: "center", animation: "fade" };
}

function TextEditor({ text, onChange }: { text: TextOverlay; onChange: (t: TextOverlay) => void }) {
  const set = (patch: Partial<TextOverlay>) => onChange({ ...text, ...patch });
  return (
    <div className="space-y-3 rounded-lg border border-line p-3">
      <p className="flex items-center gap-1 text-xs font-semibold"><Type className="h-3.5 w-3.5" /> Text overlay</p>
      <Textarea rows={2} value={text.content} onChange={(e) => set({ content: e.target.value })} />
      <div className="grid grid-cols-2 gap-3">
        <Field label="Position"><Select value={text.position} onChange={(e) => set({ position: e.target.value })}>{POSITIONS.map((p) => <option key={p} value={p}>{p.replace("_", " ")}</option>)}</Select></Field>
        <Field label="Animation"><Select value={text.animation} onChange={(e) => set({ animation: e.target.value as TextOverlay["animation"] })}>{["none", "fade", "slide_up", "typewriter"].map((a) => <option key={a} value={a}>{a}</option>)}</Select></Field>
        <Field label={`Size · ${text.font_size}px`}><Slider min={16} max={160} step={2} value={text.font_size} onChange={(v) => set({ font_size: Math.round(v) })} /></Field>
        <Field label="Font"><Select value={text.font_family} onChange={(e) => set({ font_family: e.target.value })}>{["DejaVu Sans", "DejaVu Serif", "DejaVu Sans Mono", "Liberation Sans"].map((f) => <option key={f}>{f}</option>)}</Select></Field>
        <Field label="Color"><ColorInput value={text.color} onChange={(v) => set({ color: v })} /></Field>
        <Field label="Background"><div className="flex items-center gap-2"><ColorInput value={text.background ?? "#000000"} onChange={(v) => set({ background: v })} /><Toggle checked={!!text.background} onChange={(v) => set({ background: v ? "#000000" : null })} /></div></Field>
      </div>
    </div>
  );
}

export function ColorInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center gap-2">
      <input type="color" value={value} onChange={(e) => onChange(e.target.value.toUpperCase())} className="h-8 w-10 cursor-pointer rounded border border-line bg-transparent p-0.5" />
      <Input className="font-mono uppercase" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

/* -------------------------------------------------------------------- AI */
function AIPanel({ p, scene, clip }: { p: ProjectDetail; scene: Scene | null; clip: Clip | null }) {
  const qc = useQueryClient();
  const [prompt, setPrompt] = useState(scene?.image_prompt ?? "");
  const [visualType, setVisualType] = useState(scene?.visual_type ?? p.settings?.visuals?.mode ?? "ai_image");
  const [narration, setNarration] = useState(scene?.narration ?? "");
  const busy = p.active_job && !["COMPLETED", "FAILED", "CANCELLED"].includes(String(p.active_job.state));
  const regenVisual = useMutation({
    mutationFn: () => api.scenes.generateVisuals(p.id, { scene_ids: [scene!.id], force: true, prompt_override: prompt || undefined, visual_type: visualType }),
    onSuccess: () => toast.success("Regenerating visual — the timeline refreshes when it lands"),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed"),
  });
  const regenVoice = useMutation({
    mutationFn: async () => {
      if (narration !== scene!.narration) await api.scenes.update(p.id, scene!.id, { narration });
      return api.voiceovers.generate(p.id, { scene_ids: [scene!.id], force: true });
    },
    onSuccess: () => {
      toast.success("Regenerating voiceover");
      void qc.invalidateQueries({ queryKey: ["scenes", p.id] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed"),
  });
  const allVisuals = useMutation({ mutationFn: () => api.scenes.generateVisuals(p.id), onSuccess: () => toast.success("Generating missing visuals"), onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed") });
  const allVoices = useMutation({ mutationFn: () => api.voiceovers.generate(p.id), onSuccess: () => toast.success("Generating missing voiceovers"), onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed") });
  const allCaptions = useMutation({ mutationFn: () => api.captions.generate(p.id), onSuccess: () => toast.success("Regenerating captions"), onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed") });

  return (
    <div className="space-y-5">
      {scene ? (
        <>
          <div>
            <p className="text-sm font-semibold">Scene {scene.order_index + 1}{scene.title ? ` · ${scene.title}` : ""}</p>
            <p className="text-xs text-muted">Regenerate assets for the selected scene. Costs credits per generation.</p>
          </div>
          <div className="space-y-2 rounded-lg border border-line p-3">
            <p className="flex items-center gap-1 text-xs font-semibold"><ImageIcon className="h-3.5 w-3.5" /> Visual</p>
            <Select value={visualType} onChange={(e) => setVisualType(e.target.value)}>{[["ai_image", "AI image (4 cr)"], ["ai_video", "AI video clip (25 cr)"], ["text_card", "Text card (free)"]].map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
            <Textarea rows={4} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe the shot…" />
            <Button size="sm" variant="primary" className="w-full" loading={regenVisual.isPending} disabled={!!busy} onClick={() => regenVisual.mutate()}><Wand2 className="h-3.5 w-3.5" /> {scene.visual_asset_id ? "Regenerate visual" : "Generate visual"}</Button>
          </div>
          <div className="space-y-2 rounded-lg border border-line p-3">
            <p className="flex items-center gap-1 text-xs font-semibold"><Mic2 className="h-3.5 w-3.5" /> Narration</p>
            <Textarea rows={4} value={narration} onChange={(e) => setNarration(e.target.value)} />
            <Button size="sm" variant="primary" className="w-full" loading={regenVoice.isPending} disabled={!!busy} onClick={() => regenVoice.mutate()}><RefreshCw className="h-3.5 w-3.5" /> {narration !== scene.narration ? "Save & re-voice" : "Regenerate voiceover"}</Button>
            {scene.voiceover_duration && <p className="text-[11px] text-muted">Current voiceover: {formatDuration(scene.voiceover_duration)}</p>}
          </div>
        </>
      ) : (
        <Alert tone="info">{clip ? "This clip is not linked to a scene." : "Select a scene clip on the video track to regenerate its visual or narration."}</Alert>
      )}
      <div className="space-y-2 rounded-lg border border-line p-3">
        <p className="flex items-center gap-1 text-xs font-semibold"><Sparkles className="h-3.5 w-3.5" /> Whole project</p>
        <Button size="sm" className="w-full" loading={allVisuals.isPending} disabled={!!busy} onClick={() => allVisuals.mutate()}><ImageIcon className="h-3.5 w-3.5" /> Generate missing visuals</Button>
        <Button size="sm" className="w-full" loading={allVoices.isPending} disabled={!!busy} onClick={() => allVoices.mutate()}><Mic2 className="h-3.5 w-3.5" /> Generate missing voiceovers</Button>
        <Button size="sm" className="w-full" loading={allCaptions.isPending} disabled={!!busy} onClick={() => allCaptions.mutate()}><CaptionsIcon className="h-3.5 w-3.5" /> Rebuild captions from narration</Button>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- captions */
function CaptionsPanel({ p, captions }: { p: ProjectDetail; captions: Captions | null }) {
  const { doc, updateDoc } = useEditor();
  const qc = useQueryClient();
  const style = doc?.captions;
  const set = (patch: Partial<CaptionStyleSettings>) => style && updateDoc({ captions: { ...style, ...patch } });
  const saveStyle = useMutation({
    mutationFn: () => api.captions.update(p.id, { style }),
    onSuccess: () => {
      toast.success("Caption style saved");
      void qc.invalidateQueries({ queryKey: ["captions", p.id] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed"),
  });
  if (!style) return null;
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Captions</p>
        <span className="text-xs text-muted">{captions ? `${captions.cue_count} cues · ${captions.language}` : "not generated"}</span>
      </div>
      <div className="flex gap-4">
        <Toggle checked={style.enabled} onChange={(v) => set({ enabled: v })} label="Show" />
        <Toggle checked={style.burn_in} onChange={(v) => set({ burn_in: v })} label="Burn into video" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Font"><Select value={style.font_family} onChange={(e) => set({ font_family: e.target.value })}>{["DejaVu Sans", "DejaVu Serif", "DejaVu Sans Mono", "Liberation Sans"].map((f) => <option key={f}>{f}</option>)}</Select></Field>
        <Field label={`Size · ${style.font_size}px`}><Slider min={20} max={100} step={1} value={style.font_size} onChange={(v) => set({ font_size: Math.round(v) })} /></Field>
        <Field label="Position"><Select value={style.position} onChange={(e) => set({ position: e.target.value as CaptionStyleSettings["position"] })}>{["bottom", "center", "top"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
        <Field label="Animation"><Select value={style.animation} onChange={(e) => set({ animation: e.target.value as CaptionStyleSettings["animation"] })}>{["none", "fade", "pop", "karaoke"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
        <Field label="Text color"><ColorInput value={style.color} onChange={(v) => set({ color: v })} /></Field>
        <Field label="Outline color"><ColorInput value={style.outline_color} onChange={(v) => set({ outline_color: v })} /></Field>
        <Field label={`Outline · ${style.outline_width}px`}><Slider min={0} max={8} step={0.5} value={style.outline_width} onChange={(v) => set({ outline_width: v })} /></Field>
        <Field label={`Bottom margin · ${style.margin_v}px`}><Slider min={0} max={400} step={5} value={style.margin_v} onChange={(v) => set({ margin_v: Math.round(v) })} /></Field>
        <Field label="Background"><div className="flex items-center gap-2"><ColorInput value={style.background_color ?? "#000000"} onChange={(v) => set({ background_color: v })} /><Toggle checked={!!style.background_color} onChange={(v) => set({ background_color: v ? "#000000" : null })} /></div></Field>
        <Field label="Highlight (karaoke)"><ColorInput value={style.highlight_color} onChange={(v) => set({ highlight_color: v })} /></Field>
        <Field label={`Chars / line · ${style.max_chars_per_line}`}><Slider min={16} max={90} step={1} value={style.max_chars_per_line} onChange={(v) => set({ max_chars_per_line: Math.round(v) })} /></Field>
        <Field label={`Lines · ${style.max_lines}`}><Slider min={1} max={3} step={1} value={style.max_lines} onChange={(v) => set({ max_lines: Math.round(v) })} /></Field>
        <Field label={`Timing offset · ${style.timing_offset.toFixed(2)}s`} className="col-span-2"><Slider min={-2} max={2} step={0.05} value={style.timing_offset} onChange={(v) => set({ timing_offset: v })} /></Field>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="primary" loading={saveStyle.isPending} onClick={() => saveStyle.mutate()}>Save style</Button>
        {captions && (
          <>
            <a className="btn-secondary px-2.5 py-1.5 text-xs" href={captions.srt_url || api.captions.exportUrl(p.id, "srt")} target="_blank" rel="noreferrer"><Download className="h-3.5 w-3.5" /> SRT</a>
            <a className="btn-secondary px-2.5 py-1.5 text-xs" href={captions.vtt_url || api.captions.exportUrl(p.id, "vtt")} target="_blank" rel="noreferrer"><Download className="h-3.5 w-3.5" /> VTT</a>
          </>
        )}
      </div>
      <p className="text-[11px] text-muted">Style changes are stored in the timeline (saved with ⌘S) and applied by the renderer; “Save style” also updates the caption document used for SRT/VTT export.</p>
    </div>
  );
}

/* ------------------------------------------------------------------ audio */
function AudioPanel({ p }: { p: ProjectDetail }) {
  const { doc, updateTrack, addClip, addTrack, updateDoc } = useEditor();
  const library = useQuery({ queryKey: ["audio-library"], queryFn: () => api.media.audio({ kind: "music" }) });
  const musicTrack = doc?.tracks.find((t) => t.kind === "music");
  const voTrack = doc?.tracks.find((t) => t.kind === "voiceover");
  const musicClip = musicTrack?.clips[0];
  const applyMusic = (assetId: string, url: string | null, name: string) => {
    if (!doc) return;
    const trackId = musicTrack?.id ?? addTrack("music", "Music");
    const d = useEditor.getState().doc!;
    const tr = d.tracks.find((t) => t.id === trackId)!;
    if (tr.clips.length) {
      useEditor.getState().updateClip(trackId, tr.clips[0].id, { asset_id: assetId, src_url: url, label: name, duration: d.duration || tr.clips[0].duration });
    } else {
      addClip(trackId, { scene_id: null, asset_id: assetId, asset_kind: "audio", start: 0, duration: d.duration || 60, trim_start: 0, trim_end: 0, volume: p.settings?.music?.volume ?? 0.12, fade_in: 1.5, fade_out: 3, transition_in: null, effect: null, text: null, label: name, src_url: url });
    }
  };
  return (
    <div className="space-y-5">
      <div className="space-y-2 rounded-lg border border-line p-3">
        <p className="flex items-center gap-1 text-xs font-semibold"><Music4 className="h-3.5 w-3.5" /> Background music</p>
        {musicClip ? (
          <>
            <p className="truncate text-xs text-muted">{musicClip.label || musicClip.asset_id}</p>
            <Field label={`Volume · ${Math.round(musicClip.volume * 100)}%`}><Slider min={0} max={1} step={0.01} value={musicClip.volume} onChange={(v) => useEditor.getState().updateClip(musicTrack!.id, musicClip.id, { volume: v })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label={`Fade in · ${musicClip.fade_in.toFixed(1)}s`}><Slider min={0} max={8} step={0.5} value={musicClip.fade_in} onChange={(v) => useEditor.getState().updateClip(musicTrack!.id, musicClip.id, { fade_in: v })} /></Field>
              <Field label={`Fade out · ${musicClip.fade_out.toFixed(1)}s`}><Slider min={0} max={8} step={0.5} value={musicClip.fade_out} onChange={(v) => useEditor.getState().updateClip(musicTrack!.id, musicClip.id, { fade_out: v })} /></Field>
            </div>
            <Toggle checked={!musicTrack!.muted} onChange={(v) => updateTrack(musicTrack!.id, { muted: !v })} label="Music enabled" />
          </>
        ) : (
          <p className="text-xs text-muted">No music yet — pick a track below.</p>
        )}
        <p className="text-[11px] text-muted">Voiceover ducking is applied automatically during rendering (sidechain compression).</p>
      </div>
      <div>
        <p className="label">Music library</p>
        <ul className="max-h-64 space-y-1 overflow-y-auto">
          {library.data?.map((a) => (
            <li key={a.id} className="flex items-center gap-2 rounded-md border border-line px-2 py-1.5 text-xs">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{a.filename.replace(/\.[a-z0-9]+$/i, "")}</p>
                <p className="truncate text-muted">{a.mood || "—"} · {formatDuration(a.duration_seconds)} {a.is_system && "· built-in"}</p>
              </div>
              {a.url && <audio src={a.url} controls className="h-7 w-28" preload="none" />}
              <Button size="sm" variant={musicClip?.asset_id === a.id ? "primary" : "secondary"} onClick={() => applyMusic(a.id, a.url, a.filename)}>{musicClip?.asset_id === a.id ? "In use" : "Use"}</Button>
            </li>
          ))}
          {library.data && !library.data.length && <li className="text-xs text-muted">Library is empty — upload music from the Media page.</li>}
        </ul>
      </div>
      {voTrack && (
        <div className="space-y-2 rounded-lg border border-line p-3">
          <p className="flex items-center gap-1 text-xs font-semibold"><Mic2 className="h-3.5 w-3.5" /> Voiceover track</p>
          <Field label={`Track volume · ${Math.round(voTrack.volume * 100)}%`}><Slider min={0} max={2} step={0.01} value={voTrack.volume} onChange={(v) => updateTrack(voTrack.id, { volume: v })} /></Field>
          <Toggle checked={!voTrack.muted} onChange={(v) => updateTrack(voTrack.id, { muted: !v })} label="Voiceover enabled" />
        </div>
      )}
      <div className="space-y-2 rounded-lg border border-line p-3">
        <p className="text-xs font-semibold">Watermark</p>
        <Toggle checked={!!doc?.watermark?.enabled} onChange={(v) => doc && updateDoc({ watermark: { ...doc.watermark, enabled: v } })} label="Show watermark" />
        {doc?.watermark?.enabled && (
          <>
            <Input value={doc.watermark.text ?? ""} placeholder="Channel name" onChange={(e) => updateDoc({ watermark: { ...doc.watermark, text: e.target.value } })} />
            <div className="grid grid-cols-2 gap-3">
              <Select value={doc.watermark.position} onChange={(e) => updateDoc({ watermark: { ...doc.watermark, position: e.target.value as typeof doc.watermark.position } })}>{["bottom_right", "bottom_left", "top_right", "top_left"].map((x) => <option key={x} value={x}>{x.replace("_", " ")}</option>)}</Select>
              <Slider min={0.1} max={1} step={0.05} value={doc.watermark.opacity} onChange={(v) => updateDoc({ watermark: { ...doc.watermark, opacity: v } })} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
