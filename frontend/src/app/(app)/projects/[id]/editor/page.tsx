"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Save, RefreshCw, Film, Loader2, ArrowLeft, Clapperboard, Eye, CheckCircle2, AlertTriangle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useEditor } from "@/store/editor";
import { useProject } from "@/hooks/useProject";
import { Preview } from "@/components/editor/Preview";
import { TimelinePanel } from "@/components/editor/TimelinePanel";
import { Inspector } from "@/components/editor/Inspector";
import { LeftPanel } from "@/components/editor/LeftPanel";
import { Button, JobStateBadge, ProgressBar, Spinner } from "@/components/ui";
import { cn, formatDuration, formatEta } from "@/lib/utils";

export default function EditorPage({ params }: { params: { id: string } }) {
  const pid = params.id;
  const qc = useQueryClient();
  const { project, activeJobs } = useProject(pid);
  const timeline = useQuery({ queryKey: ["timeline", pid], queryFn: () => api.timeline.get(pid) });
  const scenes = useQuery({ queryKey: ["scenes", pid], queryFn: () => api.scenes.list(pid) });
  const captions = useQuery({ queryKey: ["captions", pid], queryFn: () => api.captions.get(pid), retry: false });
  const renders = useQuery({ queryKey: ["renders", pid], queryFn: () => api.render.list(pid), refetchInterval: (q) => (q.state.data?.some((r) => !["COMPLETED", "FAILED", "CANCELLED"].includes(r.state)) ? 5000 : false) });
  const { doc, dirty, baseVersion, load, markSaved, setSaving, saving, undo, redo, playing, setPlaying, setPlayhead, playhead, selectedClipId, selectedTrackId, deleteClip, splitClipAt, duplicateClip } = useEditor();
  const [muted, setMuted] = useState(false);
  const [leftW] = useState(280);
  const [rightW] = useState(340);
  const [bottomH, setBottomH] = useState(300);
  const loadedVersion = useRef<number | null>(null);

  // Load the timeline into the editor once (and again when the server version changes while we have no local edits).
  useEffect(() => {
    if (!timeline.data) return;
    const tl = timeline.data;
    if (loadedVersion.current === null || (!useEditor.getState().dirty && tl.version !== loadedVersion.current)) {
      load(pid, tl.data, tl.version);
      loadedVersion.current = tl.version;
    }
  }, [timeline.data, pid, load]);

  const save = useMutation({
    mutationFn: async () => {
      const st = useEditor.getState();
      if (!st.doc) throw new Error("Nothing to save");
      setSaving(true);
      try {
        return await api.timeline.save(pid, st.doc, st.baseVersion ?? undefined);
      } finally {
        setSaving(false);
      }
    },
    onSuccess: (tl) => {
      markSaved(tl.version);
      loadedVersion.current = tl.version;
      qc.setQueryData(["timeline", pid], tl);
      toast.success(`Timeline saved (v${tl.version})`);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) toast.error("The timeline changed on the server (another tab or a generation job). Reload to pick up the latest version.", { duration: 8000 });
      else toast.error(e instanceof Error ? e.message : "Save failed");
    },
  });

  const resync = useMutation({
    mutationFn: () => api.timeline.sync(pid),
    onSuccess: (tl) => {
      load(pid, tl.data, tl.version);
      loadedVersion.current = tl.version;
      qc.setQueryData(["timeline", pid], tl);
      toast.success("Timeline rebuilt from the storyboard");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Sync failed"),
  });

  const render = useMutation({
    mutationFn: async (preview: boolean) => {
      const st = useEditor.getState();
      if (st.dirty) {
        const tl = await api.timeline.save(pid, st.doc!, st.baseVersion ?? undefined);
        markSaved(tl.version);
        loadedVersion.current = tl.version;
      }
      const range = preview && st.selectedClipId ? findClipRange(st.doc!, st.selectedClipId) : null;
      return api.render.start(pid, { preview, resolution: preview ? "720p" : undefined, range_start: range?.start, range_end: range?.end, idempotency_key: `${preview ? "preview" : "final"}-${pid}-${Date.now()}` });
    },
    onSuccess: (job, preview) => {
      toast.success(preview ? "Preview render queued" : "Final render queued");
      void qc.invalidateQueries({ queryKey: ["renders", pid] });
      void qc.invalidateQueries({ queryKey: ["project", pid] });
      void job;
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Render failed to start"),
  });

  // keyboard shortcuts
  const onKey = useCallback(
    (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (e.target as HTMLElement)?.isContentEditable) return;
      const mod = e.metaKey || e.ctrlKey;
      if (e.code === "Space") {
        e.preventDefault();
        setPlaying(!playing);
      } else if (mod && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
      } else if (mod && e.key.toLowerCase() === "y") {
        e.preventDefault();
        redo();
      } else if (mod && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (dirty) save.mutate();
      } else if (mod && e.key.toLowerCase() === "d") {
        e.preventDefault();
        if (selectedClipId && selectedTrackId) duplicateClip(selectedTrackId, selectedClipId);
      } else if ((e.key === "Delete" || e.key === "Backspace") && selectedClipId && selectedTrackId) {
        e.preventDefault();
        deleteClip(selectedTrackId, selectedClipId);
      } else if (e.key.toLowerCase() === "s" && selectedClipId && selectedTrackId) {
        splitClipAt(selectedTrackId, selectedClipId, playhead);
      } else if (e.key === "Home") {
        setPlayhead(0);
      } else if (e.key === "End") {
        setPlayhead(doc?.duration ?? 0);
      } else if (e.key === "ArrowLeft") {
        setPlayhead(playhead - (e.shiftKey ? 1 : 1 / (doc?.fps ?? 30)));
      } else if (e.key === "ArrowRight") {
        setPlayhead(playhead + (e.shiftKey ? 1 : 1 / (doc?.fps ?? 30)));
      }
    },
    [playing, setPlaying, undo, redo, dirty, save, selectedClipId, selectedTrackId, duplicateClip, deleteClip, splitClipAt, playhead, setPlayhead, doc],
  );
  useEffect(() => {
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onKey]);

  // warn before leaving with unsaved edits
  useEffect(() => {
    const h = (e: BeforeUnloadEvent) => {
      if (useEditor.getState().dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, []);

  // bottom panel resize
  const dragRef = useRef<{ y: number; h: number } | null>(null);
  useEffect(() => {
    const move = (e: MouseEvent) => dragRef.current && setBottomH(Math.max(160, Math.min(600, dragRef.current.h + (dragRef.current.y - e.clientY))));
    const up = () => (dragRef.current = null);
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, []);

  const p = project.data;
  const activeRender = renders.data?.find((r) => !["COMPLETED", "FAILED", "CANCELLED"].includes(r.state));
  const liveRender = activeJobs.find((j) => j.job_type.startsWith("render"));
  const lastPreview = renders.data?.find((r) => r.is_preview && r.state === "COMPLETED" && r.output_url);
  const serverAhead = timeline.data && loadedVersion.current !== null && timeline.data.version > loadedVersion.current;

  if (project.isLoading || timeline.isLoading || !doc || !p) {
    return (
      <div className="grid h-full place-items-center">
        {timeline.isError ? <p className="text-sm text-red-300">{(timeline.error as Error).message}</p> : <div className="flex items-center gap-2 text-sm text-muted"><Spinner /> Loading editor…</div>}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* editor toolbar */}
      <div className="flex h-11 items-center gap-2 border-b border-line bg-panel px-3">
        <Link href={`/projects/${pid}`} className="btn-ghost h-8 px-2 text-xs"><ArrowLeft className="h-3.5 w-3.5" /> {p.title}</Link>
        <span className="text-[11px] text-muted">v{baseVersion} · {formatDuration(doc.duration)} · {doc.width}×{doc.height}</span>
        {dirty && <span className="badge border-amber-500/40 bg-amber-500/10 text-amber-200">unsaved</span>}
        {serverAhead && !dirty && <span className="badge border-sky-500/40 bg-sky-500/10 text-sky-200">updated on server</span>}
        {serverAhead && dirty && (
          <button className="badge border-amber-500/40 bg-amber-500/10 text-amber-200" onClick={() => { if (confirm("Discard local edits and load the newer server timeline?")) { load(pid, timeline.data!.data, timeline.data!.version); loadedVersion.current = timeline.data!.version; } }}>
            <AlertTriangle className="h-3 w-3" /> newer version on server — click to reload
          </button>
        )}
        <div className="ml-auto flex items-center gap-2">
          {(activeRender || liveRender) && (
            <div className="flex w-64 items-center gap-2 rounded-md border border-line px-2 py-1">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-brand-300" />
              <div className="min-w-0 flex-1">
                <div className="flex justify-between text-[10px]"><span className="truncate">{liveRender?.message || activeRender?.message || "Rendering"}</span><span className="tabular-nums text-muted">{liveRender?.progress ?? activeRender?.progress ?? 0}%</span></div>
                <ProgressBar value={liveRender?.progress ?? activeRender?.progress ?? 0} className="mt-0.5" animated />
              </div>
              {liveRender?.eta_seconds != null && <span className="text-[10px] text-muted">{formatEta(liveRender.eta_seconds)}</span>}
              <JobStateBadge state={liveRender?.state ?? activeRender?.state ?? "QUEUED"} />
            </div>
          )}
          {lastPreview && !activeRender && (
            <a href={lastPreview.output_url!} target="_blank" rel="noreferrer" className="btn-ghost h-8 px-2 text-xs" title="Open last preview render"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-300" /> Preview ready</a>
          )}
          <Button size="sm" onClick={() => resync.mutate()} loading={resync.isPending} title="Rebuild the video/voiceover/text tracks from the storyboard (keeps music & captions settings)"><RefreshCw className="h-3.5 w-3.5" /> Sync scenes</Button>
          <Button size="sm" variant={dirty ? "primary" : "secondary"} onClick={() => save.mutate()} loading={saving} disabled={!dirty}><Save className="h-3.5 w-3.5" /> Save</Button>
          <Button size="sm" onClick={() => render.mutate(true)} loading={render.isPending && render.variables === true} disabled={!!activeRender} title={selectedClipId ? "Render a 720p preview of the selected clip" : "Render a 720p preview of the whole timeline"}><Eye className="h-3.5 w-3.5" /> Preview render</Button>
          <Button size="sm" variant="primary" onClick={() => render.mutate(false)} loading={render.isPending && render.variables === false} disabled={!!activeRender}><Film className="h-3.5 w-3.5" /> Export</Button>
          <Link href={`/projects/${pid}/export`} className="btn-ghost h-8 px-2 text-xs"><Clapperboard className="h-3.5 w-3.5" /> Renders</Link>
        </div>
      </div>

      {/* main area */}
      <div className="flex min-h-0 flex-1">
        <aside style={{ width: leftW }} className="shrink-0 border-r border-line bg-panel"><LeftPanel p={p} scenes={scenes.data ?? []} /></aside>
        <section className="flex min-w-0 flex-1 flex-col">
          <div className="min-h-0 flex-1">
            <Preview cues={captions.data?.cues ?? []} muted={muted} onToggleMute={() => setMuted((m) => !m)} />
          </div>
        </section>
        <aside style={{ width: rightW }} className="shrink-0 border-l border-line bg-panel"><Inspector p={p} scenes={scenes.data ?? []} captions={captions.data ?? null} /></aside>
      </div>

      {/* timeline */}
      <div className={cn("relative shrink-0 border-t border-line")} style={{ height: bottomH }}>
        <div className="absolute -top-1 left-0 right-0 z-30 h-2 cursor-row-resize" onMouseDown={(e) => (dragRef.current = { y: e.clientY, h: bottomH })} />
        <TimelinePanel cues={captions.data?.cues ?? []} />
      </div>
    </div>
  );
}

function findClipRange(doc: { tracks: { clips: { id: string; start: number; duration: number }[] }[] }, clipId: string): { start: number; end: number } | null {
  for (const t of doc.tracks) {
    const c = t.clips.find((x) => x.id === clipId);
    if (c) return { start: c.start, end: c.start + c.duration };
  }
  return null;
}
