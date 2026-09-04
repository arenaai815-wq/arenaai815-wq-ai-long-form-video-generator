"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Download, Film, Play, RotateCcw, XCircle, FileText, Clock3, HardDrive, Monitor, Eye, ScrollText } from "lucide-react";
import { ProjectShell } from "@/components/project/ProjectShell";
import { api, ApiError } from "@/lib/api";
import { useProject } from "@/hooks/useProject";
import type { ProjectDetail, RenderJob } from "@/types/api";
import { Alert, Button, Card, CardHeader, EmptyState, Field, JobStateBadge, Modal, ProgressBar, Select, Toggle } from "@/components/ui";
import { cn, formatBytes, formatDate, formatDuration, formatEta, formatRelative } from "@/lib/utils";

export default function ExportPage({ params }: { params: { id: string } }) {
  return <ProjectShell projectId={params.id}>{(p) => <ExportView p={p} />}</ProjectShell>;
}

function ExportView({ p }: { p: ProjectDetail }) {
  const qc = useQueryClient();
  const { live } = useProject(p.id);
  const renders = useQuery({ queryKey: ["renders", p.id], queryFn: () => api.render.list(p.id), refetchInterval: (q) => (q.state.data?.some((r) => !["COMPLETED", "FAILED", "CANCELLED"].includes(r.state)) ? 4000 : false) });
  const exportInfo = useQuery({ queryKey: ["export", p.id, p.final_video_asset_id], queryFn: () => api.projects.export(p.id), enabled: !!p.final_video_asset_id, retry: false });
  const captions = useQuery({ queryKey: ["captions", p.id], queryFn: () => api.captions.get(p.id), retry: false });
  const [opts, setOpts] = useState({ resolution: p.resolution, fps: 30, burn_captions: p.settings?.captions?.burn_in ?? true, include_watermark: p.settings?.watermark?.enabled ?? false });
  const [logsFor, setLogsFor] = useState<string | null>(null);

  const start = useMutation({
    mutationFn: (preview: boolean) => api.render.start(p.id, { preview, resolution: preview ? "720p" : opts.resolution, fps: opts.fps, burn_captions: opts.burn_captions, include_watermark: opts.include_watermark, idempotency_key: `${preview ? "preview" : "final"}-${p.id}-${Date.now()}` }),
    onSuccess: (_j, preview) => {
      toast.success(preview ? "Preview render queued" : "Final render queued");
      void qc.invalidateQueries({ queryKey: ["renders", p.id] });
      void qc.invalidateQueries({ queryKey: ["project", p.id] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not start render"),
  });
  const cancel = useMutation({ mutationFn: (id: string) => api.jobs.cancel(id), onSuccess: () => toast("Cancellation requested"), onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed") });
  const retry = useMutation({
    mutationFn: (id: string) => api.jobs.retry(id),
    onSuccess: () => {
      toast.success("Render re-queued");
      void qc.invalidateQueries({ queryKey: ["renders", p.id] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed"),
  });

  const active = renders.data?.find((r) => !["COMPLETED", "FAILED", "CANCELLED"].includes(r.state));
  const liveEv = active ? live[active.id] : undefined;
  const finals = renders.data?.filter((r) => !r.is_preview) ?? [];
  const latestFinal = finals.find((r) => r.state === "COMPLETED" && r.output_url);
  const canRender = (p.counts?.scenes ?? 0) > 0;

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        {latestFinal || exportInfo.data ? (
          <Card className="overflow-hidden p-0">
            <video controls poster={exportInfo.data?.thumbnail_url ?? p.thumbnail_url ?? undefined} src={exportInfo.data?.url ?? latestFinal?.output_url ?? undefined} className="aspect-video w-full bg-black" />
            <div className="flex flex-wrap items-center justify-between gap-3 p-4">
              <div>
                <p className="font-semibold">{exportInfo.data?.filename ?? "Final render"}</p>
                <p className="text-xs text-muted">
                  {formatDuration(exportInfo.data?.duration_seconds ?? latestFinal?.output_duration_seconds)} · {exportInfo.data?.width ?? latestFinal?.width}×{exportInfo.data?.height ?? latestFinal?.height} · {formatBytes(exportInfo.data?.size_bytes ?? latestFinal?.output_size_bytes)}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {captions.data && (
                  <>
                    <a className="btn-secondary" href={captions.data.srt_url || api.captions.exportUrl(p.id, "srt")}><FileText className="h-4 w-4" /> SRT</a>
                    <a className="btn-secondary" href={captions.data.vtt_url || api.captions.exportUrl(p.id, "vtt")}><FileText className="h-4 w-4" /> VTT</a>
                  </>
                )}
                <a className="btn-primary" href={exportInfo.data?.url ?? latestFinal?.output_url ?? "#"} download={exportInfo.data?.filename}><Download className="h-4 w-4" /> Download MP4</a>
              </div>
            </div>
          </Card>
        ) : (
          <EmptyState icon={<Film className="h-6 w-6" />} title={active ? "Rendering your video…" : "No final render yet"} description={canRender ? "Configure the export on the right and start a render. Rendering runs on background workers; you can leave this page." : "Build the storyboard first — the render composes scenes, voiceover, visuals and captions."} />
        )}

        {active && (
          <Card>
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-sm font-semibold">{active.is_preview ? "Preview render" : "Final render"} <JobStateBadge state={liveEv?.state ?? active.state} /></p>
                <p className="truncate text-xs text-muted">{liveEv?.message ?? active.message} {liveEv?.eta_seconds != null && `· ${formatEta(liveEv.eta_seconds)}`}</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => cancel.mutate(active.id)}><XCircle className="h-4 w-4" /> Cancel</Button>
            </div>
            <ProgressBar value={liveEv?.progress ?? active.progress} className="mt-3" animated />
            <p className="mt-1 text-right font-mono text-xs text-muted">{liveEv?.progress ?? active.progress}%</p>
          </Card>
        )}

        <Card>
          <CardHeader title="Render history" description="Previews and finals, newest first." />
          {renders.data?.length ? (
            <ul className="divide-y divide-line">
              {renders.data.map((r) => (
                <RenderRow key={r.id} r={r} onRetry={() => retry.mutate(r.id)} onCancel={() => cancel.mutate(r.id)} onLogs={() => setLogsFor(r.id)} />
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">No renders yet.</p>
          )}
        </Card>
      </div>

      <div className="space-y-6">
        <Card className="sticky top-4">
          <CardHeader title="Export settings" description="Applied to the next final render." />
          <div className="space-y-4">
            <Field label="Resolution"><Select value={opts.resolution} onChange={(e) => setOpts({ ...opts, resolution: e.target.value })}>{["720p", "1080p", "1440p", "4k"].map((r) => <option key={r}>{r}</option>)}</Select></Field>
            <Field label="Frame rate"><Select value={opts.fps} onChange={(e) => setOpts({ ...opts, fps: Number(e.target.value) })}>{[24, 25, 30, 50, 60].map((f) => <option key={f} value={f}>{f} fps</option>)}</Select></Field>
            <Toggle checked={opts.burn_captions} onChange={(v) => setOpts({ ...opts, burn_captions: v })} label="Burn in captions" />
            <Toggle checked={opts.include_watermark} onChange={(v) => setOpts({ ...opts, include_watermark: v })} label="Watermark" />
            <div className="rounded-lg border border-line p-3 text-xs text-muted">
              <p className="flex items-center gap-2"><Monitor className="h-3.5 w-3.5" /> {p.aspect_ratio} · H.264 MP4 · AAC 48 kHz</p>
              <p className="mt-1 flex items-center gap-2"><Clock3 className="h-3.5 w-3.5" /> Timeline {formatDuration(p.estimated_duration_seconds)} · ≈ {Math.ceil(((p.estimated_duration_seconds ?? 0) / 60) * 6)} credits</p>
              <p className="mt-1 flex items-center gap-2"><HardDrive className="h-3.5 w-3.5" /> Higher resolutions may require a paid plan.</p>
            </div>
            <Button variant="primary" className="w-full" disabled={!canRender || !!active} loading={start.isPending && start.variables === false} onClick={() => start.mutate(false)}><Film className="h-4 w-4" /> Render final video</Button>
            <Button className="w-full" disabled={!canRender || !!active} loading={start.isPending && start.variables === true} onClick={() => start.mutate(true)}><Eye className="h-4 w-4" /> Quick 720p preview</Button>
            {!canRender && <Alert tone="warning">No scenes yet — nothing to render.</Alert>}
          </div>
        </Card>
      </div>
      <LogsModal jobId={logsFor} onClose={() => setLogsFor(null)} />
    </div>
  );
}

function RenderRow({ r, onRetry, onCancel, onLogs }: { r: RenderJob; onRetry: () => void; onCancel: () => void; onLogs: () => void }) {
  const terminal = ["COMPLETED", "FAILED", "CANCELLED"].includes(r.state);
  return (
    <li className="flex items-center gap-3 py-3">
      <div className={cn("grid h-14 w-24 shrink-0 place-items-center overflow-hidden rounded-md bg-panel2", r.state === "COMPLETED" && "bg-black")}>
        {r.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={r.thumbnail_url} alt="" className="h-full w-full object-cover" />
        ) : (
          <Film className="h-4 w-4 text-muted" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium">{r.is_preview ? "Preview" : "Final"} · {r.width}×{r.height} · {r.fps}fps</span>
          <JobStateBadge state={r.state} />
        </div>
        <p className="truncate text-xs text-muted">
          {r.state === "COMPLETED" ? `${formatDuration(r.output_duration_seconds)} · ${formatBytes(r.output_size_bytes)} · rendered in ${formatDuration(r.render_seconds)}` : r.error || r.message}
          {" · "}{formatRelative(r.created_at)} · v{r.timeline_version ?? "?"} · attempt {r.attempt}/{r.max_attempts}
        </p>
        {!terminal && <ProgressBar value={r.progress} className="mt-1.5" animated />}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Button variant="ghost" size="icon" title="Logs" onClick={onLogs}><ScrollText className="h-4 w-4" /></Button>
        {r.state === "COMPLETED" && r.output_url && (
          <>
            <a className="btn-ghost h-8 w-8 p-0" href={r.output_url} target="_blank" rel="noreferrer" title="Play"><Play className="h-4 w-4" /></a>
            <a className="btn-ghost h-8 w-8 p-0" href={r.output_url} download title="Download"><Download className="h-4 w-4" /></a>
          </>
        )}
        {(r.state === "FAILED" || r.state === "CANCELLED") && <Button variant="ghost" size="icon" title="Retry" onClick={onRetry}><RotateCcw className="h-4 w-4" /></Button>}
        {!terminal && <Button variant="ghost" size="icon" title="Cancel" onClick={onCancel}><XCircle className="h-4 w-4" /></Button>}
      </div>
    </li>
  );
}

function LogsModal({ jobId, onClose }: { jobId: string | null; onClose: () => void }) {
  const logs = useQuery({ queryKey: ["job-logs", jobId], queryFn: () => api.jobs.logs(jobId!), enabled: !!jobId });
  return (
    <Modal open={!!jobId} onClose={onClose} title="Job logs" size="lg">
      {logs.data ? (
        <div className="space-y-2">
          {logs.data.error && <Alert tone="error" title="Error">{logs.data.error}</Alert>}
          <pre className="max-h-[50vh] overflow-auto rounded-lg bg-black/40 p-3 font-mono text-[11px] leading-relaxed">
            {logs.data.logs.length ? logs.data.logs.map((l, i) => <div key={i} className={cn(l.level === "error" && "text-red-300", l.level === "warning" && "text-amber-300")}><span className="text-muted">{formatDate(l.ts)}{typeof l.elapsed_s === "number" ? ` +${l.elapsed_s.toFixed(1)}s` : ""}</span> [{l.level}] {l.message}</div>) : "No log entries."}
          </pre>
          {logs.data.error_details && <pre className="max-h-40 overflow-auto rounded-lg bg-black/40 p-3 font-mono text-[10px] text-muted">{JSON.stringify(logs.data.error_details, null, 2)}</pre>}
        </div>
      ) : (
        <p className="text-sm text-muted">Loading…</p>
      )}
    </Modal>
  );
}
