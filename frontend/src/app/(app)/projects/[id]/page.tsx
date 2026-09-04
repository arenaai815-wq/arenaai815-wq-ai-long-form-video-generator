"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { BookOpenText, FileText, LayoutPanelTop, Mic2, Image as ImageIcon, Captions, Film, Play, RotateCcw, Save, Check, ArrowRight, History } from "lucide-react";
import { ProjectShell } from "@/components/project/ProjectShell";
import { api, ApiError } from "@/lib/api";
import type { ProjectDetail, ProjectUpdate } from "@/types/api";
import { Button, Card, CardHeader, Field, Input, JobStateBadge, ProgressBar, Select, Textarea } from "@/components/ui";
import { cn, formatDate, formatDuration, formatRelative, titleCase } from "@/lib/utils";

const STAGES = [
  { key: "research", label: "Research", icon: BookOpenText, href: "/research", desc: "Facts, statistics and sources", run: (pid: string) => api.research.generate(pid) },
  { key: "script", label: "Script", icon: FileText, href: "/script", desc: "Hook, chapters, conclusion", run: (pid: string) => api.script.generate(pid) },
  { key: "scenes", label: "Storyboard", icon: LayoutPanelTop, href: "/storyboard", desc: "Scenes, prompts and timing", run: (pid: string) => api.scenes.generate(pid) },
  { key: "voiceover", label: "Voiceover", icon: Mic2, href: "/storyboard", desc: "Per-scene narration audio", run: (pid: string) => api.voiceovers.generate(pid) },
  { key: "visuals", label: "Visuals", icon: ImageIcon, href: "/storyboard", desc: "AI images / video per scene", run: (pid: string) => api.scenes.generateVisuals(pid) },
  { key: "captions", label: "Captions", icon: Captions, href: "/editor", desc: "SRT/VTT from narration", run: (pid: string) => api.captions.generate(pid) },
  { key: "render", label: "Render", icon: Film, href: "/export", desc: "Final MP4 composition", run: (pid: string) => api.render.start(pid, { preview: false }) },
] as const;

export default function ProjectOverviewPage({ params }: { params: { id: string } }) {
  const id = params.id;
  return <ProjectShell projectId={id}>{(p) => <Overview p={p} />}</ProjectShell>;
}

function Overview({ p }: { p: ProjectDetail }) {
  const qc = useQueryClient();
  const jobs = useQuery({ queryKey: ["jobs", p.id], queryFn: () => api.projects.jobs(p.id) });
  const runStage = useMutation({
    mutationFn: (key: (typeof STAGES)[number]["key"]) => STAGES.find((s) => s.key === key)!.run(p.id),
    onSuccess: (_j, key) => {
      toast.success(`${titleCase(key)} queued`);
      void qc.invalidateQueries({ queryKey: ["project", p.id] });
      void qc.invalidateQueries({ queryKey: ["jobs", p.id] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not start stage"),
  });
  const busy = p.active_job && !["COMPLETED", "FAILED", "CANCELLED"].includes(String(p.active_job.state));
  const nextIdx = STAGES.findIndex((s) => !p.pipeline?.[s.key]);

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <Card>
          <CardHeader title="Pipeline" description="Each stage can be run, reviewed and re-run independently." />
          <ol className="grid gap-2 sm:grid-cols-2">
            {STAGES.map((s, i) => {
              const done = !!p.pipeline?.[s.key];
              const isNext = i === nextIdx;
              return (
                <li key={s.key} className={cn("flex items-center gap-3 rounded-lg border p-3", done ? "border-emerald-500/30 bg-emerald-500/5" : isNext ? "border-brand-500/50 bg-brand-500/5" : "border-line")}>
                  <span className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-lg", done ? "bg-emerald-500/15 text-emerald-300" : "bg-panel2 text-muted")}>{done ? <Check className="h-4 w-4" /> : <s.icon className="h-4 w-4" />}</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{s.label}</p>
                    <p className="truncate text-xs text-muted">{stageMeta(s.key, p) || s.desc}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <Link href={`/projects/${p.id}${s.href}`} className="btn-ghost h-8 px-2 text-xs">Open</Link>
                    <Button size="sm" variant={isNext && !done ? "primary" : "ghost"} disabled={!!busy || runStage.isPending} title={done ? "Run again" : "Run stage"} onClick={() => runStage.mutate(s.key)}>
                      {done ? <RotateCcw className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                    </Button>
                  </div>
                </li>
              );
            })}
          </ol>
          {p.pipeline?.render && (
            <Link href={`/projects/${p.id}/export`} className="mt-4 flex items-center justify-between rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
              <span className="flex items-center gap-2"><Film className="h-4 w-4" /> Final video is ready</span>
              <span className="flex items-center gap-1">Download <ArrowRight className="h-4 w-4" /></span>
            </Link>
          )}
        </Card>

        <SettingsEditor p={p} />
      </div>

      <div className="space-y-6">
        <Card>
          <CardHeader title="Summary" />
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            <dt className="text-muted">Target</dt><dd>{p.target_duration_minutes} min</dd>
            <dt className="text-muted">Estimated</dt><dd>{p.estimated_duration_seconds ? formatDuration(p.estimated_duration_seconds) : "—"}</dd>
            <dt className="text-muted">Format</dt><dd>{p.aspect_ratio} · {p.resolution}</dd>
            <dt className="text-muted">Language</dt><dd>{p.language.toUpperCase()}</dd>
            <dt className="text-muted">Tone</dt><dd>{p.tone}</dd>
            <dt className="text-muted">Style</dt><dd>{p.visual_style}</dd>
            <dt className="text-muted">Script</dt><dd>{p.counts?.script_words ?? 0} words</dd>
            <dt className="text-muted">Scenes</dt><dd>{p.counts?.scenes ?? 0} · {p.counts?.voiced ?? 0} voiced · {p.counts?.visualized ?? 0} visualised</dd>
            <dt className="text-muted">Renders</dt><dd>{p.counts?.renders ?? 0}</dd>
            <dt className="text-muted">Created</dt><dd>{formatDate(p.created_at)}</dd>
          </dl>
        </Card>
        <Card>
          <CardHeader title="Job history" description="Latest first." action={<History className="h-4 w-4 text-muted" />} />
          {jobs.data?.length ? (
            <ul className="max-h-96 space-y-2 overflow-y-auto pr-1">
              {jobs.data.map((j) => (
                <li key={j.id} className="rounded-lg border border-line p-2 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{titleCase(j.job_type)}</span>
                    <JobStateBadge state={j.state} />
                  </div>
                  {!["COMPLETED", "FAILED", "CANCELLED"].includes(j.state) && <ProgressBar value={j.progress} className="mt-1.5" animated />}
                  <p className="mt-1 truncate text-muted">{j.error || j.message}</p>
                  <p className="mt-0.5 text-[10px] text-muted">{formatRelative(j.created_at)} · attempt {j.attempt}/{j.max_attempts} · {j.credits_charged} cr</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">No jobs yet.</p>
          )}
        </Card>
      </div>
    </div>
  );
}

function stageMeta(key: string, p: ProjectDetail): string | null {
  const c = p.counts || {};
  switch (key) {
    case "script":
      return c.script_words ? `${c.script_words} words` : null;
    case "scenes":
      return c.scenes ? `${c.scenes} scenes` : null;
    case "voiceover":
      return c.scenes ? `${c.voiced}/${c.scenes} scenes voiced` : null;
    case "visuals":
      return c.scenes ? `${c.visualized}/${c.scenes} scenes visualised` : null;
    case "render":
      return c.renders ? `${c.renders} render${c.renders === 1 ? "" : "s"}` : null;
    default:
      return null;
  }
}

function SettingsEditor({ p }: { p: ProjectDetail }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<ProjectUpdate>({});
  useEffect(() => {
    setForm({ title: p.title, topic: p.topic, niche: p.niche, target_audience: p.target_audience, description: p.description, language: p.language, tone: p.tone, video_format: p.video_format, target_duration_minutes: p.target_duration_minutes, aspect_ratio: p.aspect_ratio, resolution: p.resolution, visual_style: p.visual_style });
  }, [p]);
  const save = useMutation({
    mutationFn: () => api.projects.update(p.id, form),
    onSuccess: () => {
      toast.success("Project saved");
      void qc.invalidateQueries({ queryKey: ["project", p.id] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Save failed"),
  });
  const set = <K extends keyof ProjectUpdate>(k: K, v: ProjectUpdate[K]) => setForm((f) => ({ ...f, [k]: v }));
  return (
    <Card>
      <CardHeader title="Project settings" description="Changing the brief affects future generations only." action={<Button size="sm" variant="primary" loading={save.isPending} onClick={() => save.mutate()}><Save className="h-3.5 w-3.5" /> Save</Button>} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Title" className="sm:col-span-2"><Input value={form.title ?? ""} onChange={(e) => set("title", e.target.value)} /></Field>
        <Field label="Topic / brief" className="sm:col-span-2"><Textarea rows={3} value={form.topic ?? ""} onChange={(e) => set("topic", e.target.value)} /></Field>
        <Field label="Niche"><Input value={form.niche ?? ""} onChange={(e) => set("niche", e.target.value)} /></Field>
        <Field label="Audience"><Input value={form.target_audience ?? ""} onChange={(e) => set("target_audience", e.target.value)} /></Field>
        <Field label="Tone"><Input value={form.tone ?? ""} onChange={(e) => set("tone", e.target.value)} /></Field>
        <Field label="Format"><Input value={form.video_format ?? ""} onChange={(e) => set("video_format", e.target.value)} /></Field>
        <Field label="Duration (min)"><Input type="number" min={1} max={180} value={form.target_duration_minutes ?? 10} onChange={(e) => set("target_duration_minutes", Number(e.target.value))} /></Field>
        <Field label="Visual style"><Input value={form.visual_style ?? ""} onChange={(e) => set("visual_style", e.target.value)} /></Field>
        <Field label="Aspect ratio"><Select value={form.aspect_ratio ?? "16:9"} onChange={(e) => set("aspect_ratio", e.target.value)}>{["16:9", "9:16", "1:1", "4:5"].map((a) => <option key={a}>{a}</option>)}</Select></Field>
        <Field label="Resolution"><Select value={form.resolution ?? "1080p"} onChange={(e) => set("resolution", e.target.value)}>{["720p", "1080p", "1440p", "4k"].map((a) => <option key={a}>{a}</option>)}</Select></Field>
      </div>
    </Card>
  );
}
