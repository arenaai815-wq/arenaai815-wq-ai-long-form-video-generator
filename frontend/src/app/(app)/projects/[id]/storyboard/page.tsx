"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { LayoutPanelTop, Sparkles, Mic2, Image as ImageIcon, RefreshCw, Trash2, Plus, Scissors, ChevronUp, ChevronDown, ArrowRight, Play, Pause, Upload, Search, Wand2, Check, Film } from "lucide-react";
import { ProjectShell } from "@/components/project/ProjectShell";
import { api, ApiError, uploadFile } from "@/lib/api";
import type { ProjectDetail, Scene, SceneUpdate, StockSearchResult, MediaAsset, Voice } from "@/types/api";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, Modal, Select, Slider, Tabs, Textarea } from "@/components/ui";
import { cn, formatDuration } from "@/lib/utils";

const TRANSITIONS = ["fade", "fadeblack", "fadewhite", "dissolve", "wipeleft", "wiperight", "slideleft", "slideright", "smoothleft", "smoothright", "circleopen", "circleclose", "radial", "pixelize", "none"];
const MOTIONS = ["ken_burns", "zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "none"];
const VISUAL_TYPES: [string, string][] = [["ai_image", "AI image"], ["ai_video", "AI video"], ["stock_video", "Stock video"], ["stock_image", "Stock image"], ["upload", "Upload"], ["text_card", "Text card"]];

export default function StoryboardPage({ params }: { params: { id: string } }) {
  return <ProjectShell projectId={params.id} wide>{(p) => <Storyboard p={p} />}</ProjectShell>;
}

function Storyboard({ p }: { p: ProjectDetail }) {
  const qc = useQueryClient();
  const scenes = useQuery({ queryKey: ["scenes", p.id], queryFn: () => api.scenes.list(p.id) });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [genOpen, setGenOpen] = useState(false);
  const [target, setTarget] = useState(p.settings?.scene_target_seconds ?? 9);
  const running = p.active_job && !["COMPLETED", "FAILED", "CANCELLED"].includes(String(p.active_job.state));
  const list = useMemo(() => scenes.data ?? [], [scenes.data]);
  const selected = list.find((s) => s.id === selectedId) ?? list[0] ?? null;
  useEffect(() => {
    if (!selectedId && list.length) setSelectedId(list[0].id);
  }, [list, selectedId]);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["scenes", p.id] });
    void qc.invalidateQueries({ queryKey: ["project", p.id] });
  };
  const generate = useMutation({
    mutationFn: () => api.scenes.generate(p.id, { scene_target_seconds: target }),
    onSuccess: () => {
      toast.success("Breaking script into scenes…");
      setGenOpen(false);
      invalidate();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not start"),
  });
  const voiceAll = useMutation({
    mutationFn: () => api.voiceovers.generate(p.id),
    onSuccess: () => toast.success("Voiceover generation queued"),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not start"),
  });
  const visualsAll = useMutation({
    mutationFn: () => api.scenes.generateVisuals(p.id),
    onSuccess: () => toast.success("Visual generation queued"),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not start"),
  });
  const reorder = useMutation({
    mutationFn: (ids: string[]) => api.scenes.reorder(p.id, ids),
    onSuccess: (d) => qc.setQueryData(["scenes", p.id], d),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Reorder failed"),
  });
  const add = useMutation({
    mutationFn: (after: string | null) => api.scenes.create(p.id, { narration: "New scene narration.", after_scene_id: after, visual_type: (p.settings?.visuals?.mode === "ai_video" ? "ai_video" : "ai_image") }),
    onSuccess: (d) => {
      qc.setQueryData(["scenes", p.id], d);
      invalidate();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not add scene"),
  });

  const total = useMemo(() => list.reduce((a, s) => a + (s.duration_seconds || 0), 0), [list]);
  const voiced = list.filter((s) => s.voiceover_id).length;
  const visualised = list.filter((s) => s.visual_asset_id).length;

  const genModal = (
    <Modal open={genOpen} onClose={() => setGenOpen(false)} title={list.length ? "Regenerate storyboard" : "Generate storyboard"} footer={<><Button onClick={() => setGenOpen(false)}>Cancel</Button><Button variant="primary" loading={generate.isPending} onClick={() => generate.mutate()}><Sparkles className="h-4 w-4" /> Generate</Button></>}>
      <div className="space-y-4">
        {list.length > 0 && <Alert tone="warning">All scenes (including edits, voiceovers and visuals assignments) will be replaced.</Alert>}
        <Field label={`Target scene length: ${target}s`} hint="Shorter scenes = more visuals and more credits.">
          <Slider min={4} max={30} step={1} value={target} onChange={setTarget} />
        </Field>
        <p className="text-xs text-muted">≈ {Math.ceil(((p.counts?.script_words ?? 0) / 150) * 60 / target)} scenes from {p.counts?.script_words ?? 0} words.</p>
      </div>
    </Modal>
  );

  if (scenes.isLoading) return <Card><div className="skeleton h-40" /></Card>;
  if (!list.length) {
    return (
      <>
        <EmptyState icon={<LayoutPanelTop className="h-6 w-6" />} title={running ? "Building the storyboard…" : "No scenes yet"} description={p.pipeline?.script ? "Break the script into scenes with visual direction, prompts, on-screen text and timing." : "Write the script first — the storyboard is derived from it."} action={p.pipeline?.script && !running ? <Button variant="primary" onClick={() => setGenOpen(true)}><Sparkles className="h-4 w-4" /> Generate scenes</Button> : <Link href={`/projects/${p.id}/script`} className="btn-primary">Go to script</Link>} />
        {genModal}
      </>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
          <Badge>{list.length} scenes</Badge>
          <Badge>{formatDuration(total)} total</Badge>
          <Badge className={voiced === list.length ? "border-emerald-500/40 text-emerald-300" : ""}><Mic2 className="h-3 w-3" /> {voiced}/{list.length} voiced</Badge>
          <Badge className={visualised === list.length ? "border-emerald-500/40 text-emerald-300" : ""}><ImageIcon className="h-3 w-3" /> {visualised}/{list.length} visualised</Badge>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => setGenOpen(true)} disabled={!!running}><Sparkles className="h-3.5 w-3.5" /> Regenerate</Button>
          <Button size="sm" onClick={() => voiceAll.mutate()} disabled={!!running} loading={voiceAll.isPending}><Mic2 className="h-3.5 w-3.5" /> Voice all missing</Button>
          <Button size="sm" onClick={() => visualsAll.mutate()} disabled={!!running} loading={visualsAll.isPending}><ImageIcon className="h-3.5 w-3.5" /> Generate all visuals</Button>
          <Link href={`/projects/${p.id}/editor`} className="btn-primary px-3 py-1.5 text-xs">Open editor <ArrowRight className="h-3.5 w-3.5" /></Link>
        </div>
      </div>

      {/* Visual timeline strip */}
      <div className="card overflow-x-auto p-3">
        <div className="flex min-w-max items-stretch gap-1">
          {list.map((s, i) => {
            const w = Math.max(64, Math.min(320, (s.duration_seconds || 5) * 14));
            return (
              <button key={s.id} onClick={() => setSelectedId(s.id)} style={{ width: w }} className={cn("group relative h-20 shrink-0 overflow-hidden rounded-md border text-left transition", selected?.id === s.id ? "border-brand-500 ring-2 ring-brand-500/30" : "border-line hover:border-brand-500/50")} title={s.title ?? undefined}>
                {s.visual_thumbnail_url || s.visual_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={s.visual_thumbnail_url || s.visual_url || ""} alt="" className="h-full w-full object-cover" />
                ) : (
                  <div className="h-full w-full bg-[linear-gradient(135deg,rgb(var(--panel2)),rgb(var(--line)))]" />
                )}
                <span className="absolute left-1 top-1 rounded bg-black/60 px-1 font-mono text-[10px] text-white">{i + 1}</span>
                <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1 font-mono text-[10px] text-white">{formatDuration(s.duration_seconds)}</span>
                <span className="absolute bottom-1 left-1 flex gap-0.5">
                  <span className={cn("h-1.5 w-1.5 rounded-full", s.voiceover_id ? "bg-emerald-400" : "bg-zinc-500")} title="voiceover" />
                  <span className={cn("h-1.5 w-1.5 rounded-full", s.visual_asset_id ? "bg-sky-400" : "bg-zinc-500")} title="visual" />
                </span>
              </button>
            );
          })}
          <button onClick={() => add.mutate(list[list.length - 1]?.id ?? null)} className="grid h-20 w-12 shrink-0 place-items-center rounded-md border border-dashed border-line text-muted hover:border-brand-500/60 hover:text-fg" title="Add scene"><Plus className="h-4 w-4" /></button>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        {/* Scene list */}
        <div className="space-y-2">
          {list.map((s, i) => (
            <SceneRow key={s.id} s={s} index={i} count={list.length} selected={selected?.id === s.id} onSelect={() => setSelectedId(s.id)} onMove={(d) => { const ids = list.map((x) => x.id); const j = i + d; if (j < 0 || j >= ids.length) return; [ids[i], ids[j]] = [ids[j], ids[i]]; reorder.mutate(ids); }} onAddAfter={() => add.mutate(s.id)} />
          ))}
        </div>
        {/* Inspector */}
        <div className="xl:sticky xl:top-4 xl:self-start">{selected && <SceneInspector key={selected.id} p={p} s={selected} running={!!running} />}</div>
      </div>
      {genModal}
    </div>
  );
}

function SceneRow({ s, index, count, selected, onSelect, onMove, onAddAfter }: { s: Scene; index: number; count: number; selected: boolean; onSelect: () => void; onMove: (d: -1 | 1) => void; onAddAfter: () => void }) {
  return (
    <div onClick={onSelect} className={cn("card flex cursor-pointer gap-3 p-3 transition", selected ? "border-brand-500/60" : "hover:border-brand-500/30")}>
      <div className="relative aspect-video w-40 shrink-0 overflow-hidden rounded-md bg-panel2">
        {s.visual_thumbnail_url || s.visual_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={s.visual_thumbnail_url || s.visual_url || ""} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="grid h-full w-full place-items-center text-muted"><ImageIcon className="h-5 w-5" /></div>
        )}
        <span className="absolute left-1 top-1 rounded bg-black/60 px-1 font-mono text-[10px] text-white">{index + 1}</span>
        {s.on_screen_text && <span className="absolute bottom-1 left-1 right-1 truncate rounded bg-black/60 px-1 text-[10px] text-white">{s.on_screen_text}</span>}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium">{s.title || `Scene ${index + 1}`}</p>
          <Badge className="shrink-0">{VISUAL_TYPES.find(([k]) => k === s.visual_type)?.[1] ?? s.visual_type}</Badge>
          <span className="ml-auto shrink-0 font-mono text-xs text-muted">{formatDuration(s.duration_seconds)}</span>
        </div>
        <p className="mt-1 line-clamp-2 text-xs text-muted">{s.narration}</p>
        <div className="mt-1.5 flex items-center gap-2 text-[11px]">
          <span className={cn("flex items-center gap-1", s.voiceover_id ? "text-emerald-300" : "text-muted")}><Mic2 className="h-3 w-3" /> {s.voiceover_id ? `${formatDuration(s.voiceover_duration)} audio` : "no voiceover"}</span>
          <span className={cn("flex items-center gap-1", s.visual_asset_id ? "text-sky-300" : "text-muted")}><ImageIcon className="h-3 w-3" /> {s.visual_asset_id ? s.visual_kind || "visual" : "no visual"}</span>
          <span className="text-muted">· {s.transition} · {s.motion_effect}</span>
          {s.status === "failed" && <span className="text-red-300">· failed</span>}
        </div>
      </div>
      <div className="flex shrink-0 flex-col gap-0.5">
        <Button variant="ghost" size="icon" disabled={index === 0} onClick={(e) => { e.stopPropagation(); onMove(-1); }}><ChevronUp className="h-4 w-4" /></Button>
        <Button variant="ghost" size="icon" disabled={index === count - 1} onClick={(e) => { e.stopPropagation(); onMove(1); }}><ChevronDown className="h-4 w-4" /></Button>
        <Button variant="ghost" size="icon" title="Insert scene after" onClick={(e) => { e.stopPropagation(); onAddAfter(); }}><Plus className="h-4 w-4" /></Button>
      </div>
    </div>
  );
}

function SceneInspector({ p, s, running }: { p: ProjectDetail; s: Scene; running: boolean }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"script" | "visual" | "audio" | "timing">("script");
  const [form, setForm] = useState<SceneUpdate>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [stockOpen, setStockOpen] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [splitAt, setSplitAt] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const voices = useQuery({ queryKey: ["voices", p.language], queryFn: () => api.voiceovers.voices({ language: p.language }) });

  const v = <K extends keyof SceneUpdate>(k: K): NonNullable<Scene[K & keyof Scene]> | SceneUpdate[K] => (k in form ? form[k] : (s[k as keyof Scene] as never));
  const save = useMutation({
    mutationFn: (body: SceneUpdate) => api.scenes.update(p.id, s.id, body),
    onSuccess: (d) => {
      qc.setQueryData<Scene[]>(["scenes", p.id], (old) => old?.map((x) => (x.id === d.id ? d : x)));
      setForm({});
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Save failed"),
  });
  const setField = <K extends keyof SceneUpdate>(k: K, val: SceneUpdate[K], immediate = false) => {
    setForm((f) => ({ ...f, [k]: val }));
    if (timer.current) clearTimeout(timer.current);
    if (immediate) save.mutate({ [k]: val } as SceneUpdate);
    else timer.current = setTimeout(() => save.mutate({ ...form, [k]: val }), 800);
  };
  const setList = (d: Scene[]) => {
    qc.setQueryData(["scenes", p.id], d);
    void qc.invalidateQueries({ queryKey: ["project", p.id] });
  };
  const del = useMutation({ mutationFn: () => api.scenes.remove(p.id, s.id), onSuccess: setList, onError: (e) => toast.error(e instanceof ApiError ? e.message : "Delete failed") });
  const split = useMutation({ mutationFn: (at: number) => api.scenes.split(p.id, s.id, at), onSuccess: (d) => { setList(d); setSplitAt(null); toast.success("Scene split"); }, onError: (e) => toast.error(e instanceof ApiError ? e.message : "Split failed") });
  const regenVisual = useMutation({
    mutationFn: (override?: string) => api.scenes.generateVisuals(p.id, { scene_ids: [s.id], force: true, prompt_override: override, visual_type: (form.visual_type ?? s.visual_type) as string }),
    onSuccess: () => toast.success("Generating visual for this scene…"),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not start"),
  });
  const regenVoice = useMutation({
    mutationFn: (voice_id?: string) => api.voiceovers.generate(p.id, { scene_ids: [s.id], force: true, voice_id }),
    onSuccess: () => toast.success("Generating voiceover for this scene…"),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not start"),
  });
  const clearVisual = useMutation({
    mutationFn: () => api.scenes.clearVisual(p.id, s.id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["scenes", p.id] }); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed"),
  });
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const asset = await uploadFile(file, { project_id: p.id });
      return api.scenes.visualFromAsset(p.id, s.id, asset.id);
    },
    onSuccess: (d) => { qc.setQueryData<Scene[]>(["scenes", p.id], (old) => old?.map((x) => (x.id === d.id ? d : x))); toast.success("Upload assigned to scene"); },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Upload failed"),
  });

  const narration = (v("narration") as string) ?? "";
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <Input className="border-transparent bg-transparent px-1 font-semibold hover:border-line" value={(v("title") as string) ?? ""} placeholder={`Scene ${s.order_index + 1}`} onChange={(e) => setField("title", e.target.value)} />
        <Button variant="ghost" size="icon" title="Delete scene" onClick={() => confirm("Delete this scene?") && del.mutate()}><Trash2 className="h-4 w-4" /></Button>
      </div>
      <div className="relative mb-3 aspect-video w-full overflow-hidden rounded-lg bg-panel2">
        {s.visual_url ? (
          s.visual_kind === "video" ? <video src={s.visual_url} className="h-full w-full object-cover" controls muted loop /> : // eslint-disable-next-line @next/next/no-img-element
          <img src={s.visual_url} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="grid h-full w-full place-items-center text-xs text-muted">{s.status === "generating" || running ? "Waiting for visual…" : "No visual assigned"}</div>
        )}
        {s.on_screen_text && <div className="absolute left-3 top-3 rounded bg-black/70 px-2 py-1 text-xs font-semibold text-white">{s.on_screen_text}</div>}
      </div>
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "script", label: "Script" }, { id: "visual", label: "Visual" }, { id: "audio", label: "Audio" }, { id: "timing", label: "Timing" }]} />

      {tab === "script" && (
        <div className="mt-4 space-y-3">
          <Field label={`Narration · ${narration.trim().split(/\s+/).filter(Boolean).length} words`}>
            <Textarea rows={6} value={narration} onChange={(e) => setField("narration", e.target.value)} onSelect={(e) => setSplitAt((e.target as HTMLTextAreaElement).selectionStart || null)} />
          </Field>
          <div className="flex items-center gap-2">
            <Button size="sm" disabled={!splitAt || splitAt < 5 || splitAt > narration.length - 5} onClick={() => splitAt && split.mutate(splitAt)} title="Place the cursor in the narration and split into two scenes"><Scissors className="h-3.5 w-3.5" /> Split at cursor</Button>
            <span className="text-[11px] text-muted">{splitAt ? `at character ${splitAt}` : "click inside the narration to choose a split point"}</span>
          </div>
          <Field label="On-screen text" hint="Short headline overlay shown during this scene."><Input value={(v("on_screen_text") as string) ?? ""} onChange={(e) => setField("on_screen_text", e.target.value || null)} /></Field>
          <Field label="Keywords"><Input value={((v("keywords") as string[]) ?? []).join(", ")} onChange={(e) => setField("keywords", e.target.value.split(",").map((k) => k.trim()).filter(Boolean))} /></Field>
        </div>
      )}

      {tab === "visual" && (
        <div className="mt-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Visual type"><Select value={(v("visual_type") as string) ?? "ai_image"} onChange={(e) => setField("visual_type", e.target.value, true)}>{VISUAL_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select></Field>
            <Field label="Motion"><Select value={(v("motion_effect") as string) ?? "ken_burns"} onChange={(e) => setField("motion_effect", e.target.value, true)}>{MOTIONS.map((m) => <option key={m} value={m}>{m.replace("_", " ")}</option>)}</Select></Field>
          </div>
          <Field label="Visual description" hint="What the viewer should see (used to build prompts)."><Textarea rows={2} value={(v("visual_description") as string) ?? ""} onChange={(e) => setField("visual_description", e.target.value)} /></Field>
          <Field label="AI image prompt"><Textarea rows={3} value={(v("image_prompt") as string) ?? ""} onChange={(e) => setField("image_prompt", e.target.value)} /></Field>
          <Field label="AI video prompt"><Textarea rows={2} value={(v("video_prompt") as string) ?? ""} onChange={(e) => setField("video_prompt", e.target.value)} /></Field>
          <Field label="Negative prompt"><Input value={(v("negative_prompt") as string) ?? ""} onChange={(e) => setField("negative_prompt", e.target.value)} /></Field>
          <Field label="Suggested footage"><Input value={(v("suggested_footage") as string) ?? ""} onChange={(e) => setField("suggested_footage", e.target.value)} /></Field>
          <div className="flex flex-wrap gap-2 border-t border-line pt-3">
            <Button size="sm" variant="primary" loading={regenVisual.isPending} disabled={running} onClick={() => regenVisual.mutate(undefined)}><Wand2 className="h-3.5 w-3.5" /> {s.visual_asset_id ? "Regenerate" : "Generate"} with AI</Button>
            <Button size="sm" onClick={() => setStockOpen(true)}><Search className="h-3.5 w-3.5" /> Stock</Button>
            <Button size="sm" onClick={() => setLibraryOpen(true)}><Film className="h-3.5 w-3.5" /> Library</Button>
            <label className="btn-secondary cursor-pointer px-2.5 py-1.5 text-xs"><Upload className="h-3.5 w-3.5" /> Upload<input type="file" accept="image/*,video/*" className="hidden" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} /></label>
            {s.visual_asset_id && <Button size="sm" variant="ghost" onClick={() => clearVisual.mutate()}><Trash2 className="h-3.5 w-3.5" /> Remove</Button>}
          </div>
          {upload.isPending && <p className="text-xs text-muted">Uploading…</p>}
        </div>
      )}

      {tab === "audio" && (
        <div className="mt-4 space-y-3">
          {s.voiceover_url ? (
            <div className="flex items-center gap-2 rounded-lg border border-line p-2">
              <Button size="icon" variant="ghost" onClick={() => { const a = audioRef.current; if (!a) return; if (playing) a.pause(); else void a.play(); }}>{playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}</Button>
              <audio ref={audioRef} src={s.voiceover_url} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
              <div className="text-xs"><p className="font-medium">Voiceover ready</p><p className="text-muted">{formatDuration(s.voiceover_duration)} · {s.voiceover_status}</p></div>
              <a className="btn-ghost ml-auto text-xs" href={s.voiceover_url} download>Download</a>
            </div>
          ) : (
            <Alert tone="info">No voiceover yet for this scene.</Alert>
          )}
          <VoicePicker voices={voices.data ?? []} defaultVoice={p.settings?.voice?.voice_id} onGenerate={(vid) => regenVoice.mutate(vid)} loading={regenVoice.isPending} disabled={running} />
          <div className="grid grid-cols-2 gap-3">
            <Field label="Music mood"><Input value={(v("music_mood") as string) ?? ""} onChange={(e) => setField("music_mood", e.target.value)} /></Field>
            <Field label="Music suggestion"><Input value={(v("music_suggestion") as string) ?? ""} onChange={(e) => setField("music_suggestion", e.target.value)} /></Field>
          </div>
          <Field label="Sound effects" hint="Comma separated cues, e.g. whoosh, wind, crowd"><Input value={((v("sound_effects") as string[]) ?? []).join(", ")} onChange={(e) => setField("sound_effects", e.target.value.split(",").map((k) => k.trim()).filter(Boolean))} /></Field>
        </div>
      )}

      {tab === "timing" && (
        <div className="mt-4 space-y-3">
          <Field label={`Duration · ${formatDuration(v("duration_seconds") as number)}`} hint={s.voiceover_duration ? `Voiceover is ${formatDuration(s.voiceover_duration)}; the scene is at least that long.` : "Without a voiceover, this is the exact scene length."}>
            <Slider min={1} max={60} step={0.1} value={(v("duration_seconds") as number) ?? 8} onChange={(val) => setField("duration_seconds", val)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Transition in"><Select value={(v("transition") as string) ?? "fade"} onChange={(e) => setField("transition", e.target.value, true)}>{TRANSITIONS.map((t) => <option key={t}>{t}</option>)}</Select></Field>
            <Field label={`Transition · ${Number(v("transition_duration") ?? 0.6).toFixed(1)}s`}><Slider min={0} max={2} step={0.1} value={(v("transition_duration") as number) ?? 0.6} onChange={(val) => setField("transition_duration", val)} /></Field>
          </div>
          <p className="text-xs text-muted">Starts at {formatDuration(s.start_time)} in the timeline.</p>
        </div>
      )}
      {save.isPending && <p className="mt-2 text-[11px] text-muted">Saving…</p>}
      {save.isSuccess && !save.isPending && Object.keys(form).length === 0 && <p className="mt-2 flex items-center gap-1 text-[11px] text-emerald-300"><Check className="h-3 w-3" /> Saved</p>}

      <StockModal open={stockOpen} onClose={() => setStockOpen(false)} p={p} s={s} initial={s.keywords?.join(" ") || s.suggested_footage || ""} />
      <LibraryModal open={libraryOpen} onClose={() => setLibraryOpen(false)} p={p} s={s} />
    </Card>
  );
}

function VoicePicker({ voices, defaultVoice, onGenerate, loading, disabled }: { voices: Voice[]; defaultVoice?: string; onGenerate: (voiceId?: string) => void; loading: boolean; disabled: boolean }) {
  const [voice, setVoice] = useState(defaultVoice || "");
  const [previewing, setPreviewing] = useState(false);
  const preview = async () => {
    if (!voice) return;
    setPreviewing(true);
    try {
      const blob = await api.voiceovers.preview({ voice_id: voice, provider: voices.find((x) => x.id === voice)?.provider });
      const a = new Audio(URL.createObjectURL(blob));
      a.onended = () => setPreviewing(false);
      await a.play();
    } catch (e) {
      setPreviewing(false);
      toast.error(e instanceof Error ? e.message : "Preview failed");
    }
  };
  return (
    <div className="space-y-2">
      <Field label="Voice">
        <div className="flex gap-2">
          <Select value={voice} onChange={(e) => setVoice(e.target.value)}>
            <option value="">Project default</option>
            {voices.map((x) => <option key={x.id} value={x.id}>{x.name} · {x.gender || "–"} · {x.accent || x.language}</option>)}
          </Select>
          <Button size="sm" onClick={preview} disabled={!voice || previewing} title="Preview voice"><Play className="h-3.5 w-3.5" /></Button>
        </div>
      </Field>
      <Button size="sm" variant="primary" loading={loading} disabled={disabled} onClick={() => onGenerate(voice || undefined)}><RefreshCw className="h-3.5 w-3.5" /> Generate voiceover for this scene</Button>
    </div>
  );
}

function StockModal({ open, onClose, p, s, initial }: { open: boolean; onClose: () => void; p: ProjectDetail; s: Scene; initial: string }) {
  const qc = useQueryClient();
  const [q, setQ] = useState(initial);
  const [kind, setKind] = useState("video");
  const [term, setTerm] = useState(initial);
  const results = useQuery({ queryKey: ["stock", term, kind], queryFn: () => api.media.stockSearch({ q: term, kind, per_page: 24 }), enabled: open && term.length > 1 });
  const pick = useMutation({
    mutationFn: (item: StockSearchResult) => api.scenes.visualFromStock(p.id, s.id, item),
    onSuccess: (d) => { qc.setQueryData<Scene[]>(["scenes", p.id], (old) => old?.map((x) => (x.id === d.id ? d : x))); toast.success("Stock clip assigned"); onClose(); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Import failed"),
  });
  return (
    <Modal open={open} onClose={onClose} title="Stock footage" size="xl">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); setTerm(q); }}>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="desert dunes aerial" />
        <Select className="w-32" value={kind} onChange={(e) => setKind(e.target.value)}><option value="video">Video</option><option value="image">Photos</option></Select>
        <Button type="submit" variant="primary"><Search className="h-4 w-4" /></Button>
      </form>
      <div className="mt-4 grid max-h-[55vh] grid-cols-2 gap-2 overflow-y-auto sm:grid-cols-3 md:grid-cols-4">
        {results.isLoading && <p className="col-span-full text-sm text-muted">Searching…</p>}
        {results.data?.map((r) => (
          <button key={r.id} onClick={() => pick.mutate(r)} className="group relative aspect-video overflow-hidden rounded-md border border-line hover:border-brand-500">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {r.thumbnail_url ? <img src={r.thumbnail_url} alt="" className="h-full w-full object-cover" /> : <div className="h-full w-full bg-panel2" />}
            <span className="absolute bottom-1 left-1 rounded bg-black/60 px-1 text-[10px] text-white">{r.source}{r.duration_seconds ? ` · ${formatDuration(r.duration_seconds)}` : ""}</span>
          </button>
        ))}
        {results.data && !results.data.length && <p className="col-span-full text-sm text-muted">No results (configure STOCK_PROVIDER=pexels|pixabay for live search).</p>}
      </div>
    </Modal>
  );
}

function LibraryModal({ open, onClose, p, s }: { open: boolean; onClose: () => void; p: ProjectDetail; s: Scene }) {
  const qc = useQueryClient();
  const [scope, setScope] = useState<"project" | "all">("project");
  const media = useQuery({ queryKey: ["media", scope === "project" ? p.id : "all"], queryFn: () => api.media.list({ project_id: scope === "project" ? p.id : undefined, page_size: 60 }), enabled: open });
  const pick = useMutation({
    mutationFn: (a: MediaAsset) => api.scenes.visualFromAsset(p.id, s.id, a.id),
    onSuccess: (d) => { qc.setQueryData<Scene[]>(["scenes", p.id], (old) => old?.map((x) => (x.id === d.id ? d : x))); toast.success("Asset assigned"); onClose(); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed"),
  });
  return (
    <Modal open={open} onClose={onClose} title="Media library" size="xl">
      <Tabs value={scope} onChange={setScope} tabs={[{ id: "project", label: "This project" }, { id: "all", label: "All reusable assets" }]} className="mb-3 w-72" />
      <div className="grid max-h-[55vh] grid-cols-2 gap-2 overflow-y-auto sm:grid-cols-3 md:grid-cols-4">
        {media.data?.items.filter((a) => a.source !== "render").map((a) => (
          <button key={a.id} onClick={() => pick.mutate(a)} className="group relative aspect-video overflow-hidden rounded-md border border-line hover:border-brand-500">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {a.thumbnail_url || a.url ? <img src={a.thumbnail_url || a.url || ""} alt="" className="h-full w-full object-cover" /> : <div className="h-full w-full bg-panel2" />}
            <span className="absolute bottom-1 left-1 right-1 truncate rounded bg-black/60 px-1 text-[10px] text-white">{a.filename}</span>
          </button>
        ))}
        {media.data && !media.data.items.length && <p className="col-span-full text-sm text-muted">Nothing here yet.</p>}
      </div>
    </Modal>
  );
}
