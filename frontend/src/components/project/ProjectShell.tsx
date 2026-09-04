"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { BookOpenText, FileText, LayoutPanelTop, Clapperboard, Film, Download, Check, Loader2, Wand2, XCircle, Settings2 } from "lucide-react";
import { useProject } from "@/hooks/useProject";
import { api, ApiError } from "@/lib/api";
import { cn, formatEta, isTerminal } from "@/lib/utils";
import { Button, JobStateBadge, ProgressBar, ProjectStatusBadge, Skeleton } from "@/components/ui";
import type { ProjectDetail } from "@/types/api";

const STEPS = [
  { id: "overview", label: "Overview", icon: Settings2, href: "" },
  { id: "research", label: "Research", icon: BookOpenText, href: "/research", key: "research" },
  { id: "script", label: "Script", icon: FileText, href: "/script", key: "script" },
  { id: "storyboard", label: "Storyboard", icon: LayoutPanelTop, href: "/storyboard", key: "scenes" },
  { id: "editor", label: "Editor", icon: Clapperboard, href: "/editor", key: "visuals" },
  { id: "export", label: "Render & export", icon: Download, href: "/export", key: "render" },
] as const;

export function ProjectShell({ projectId, children, wide }: { projectId: string; children: (p: ProjectDetail) => React.ReactNode; wide?: boolean }) {
  const pathname = usePathname();
  const qc = useQueryClient();
  const { project, activeJobs } = useProject(projectId);
  const p = project.data;
  const current = STEPS.find((s) => s.href && pathname.endsWith(s.href))?.id ?? "overview";
  const live = activeJobs[0] ?? null;
  const job = live ?? (p?.active_job && !isTerminal(String(p.active_job.state)) ? (p.active_job as never) : null);

  const cancel = useMutation({
    mutationFn: (id: string) => api.jobs.cancel(id),
    onSuccess: () => toast("Cancellation requested"),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not cancel"),
  });
  const run = useMutation({
    mutationFn: () => api.projects.generate(projectId, { idempotency_key: `pipeline-${projectId}-${Date.now()}` }),
    onSuccess: () => {
      toast.success("Pipeline started");
      void qc.invalidateQueries({ queryKey: ["project", projectId] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not start pipeline"),
  });

  if (project.isError) {
    return <div className="mx-auto max-w-3xl"><p className="text-sm text-red-300">{(project.error as Error).message}</p></div>;
  }

  return (
    <div className={cn("mx-auto", wide ? "max-w-[1600px]" : "max-w-6xl")}>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          {p ? (
            <>
              <div className="flex items-center gap-2">
                <h1 className="truncate text-xl font-semibold tracking-tight">{p.title}</h1>
                <ProjectStatusBadge status={p.status} />
              </div>
              <p className="mt-1 line-clamp-1 max-w-3xl text-sm text-muted">{p.topic}</p>
            </>
          ) : (
            <Skeleton className="h-7 w-72" />
          )}
        </div>
        <div className="flex items-center gap-2">
          {job ? (
            <div className="flex items-center gap-3 rounded-lg border border-line bg-panel px-3 py-2">
              <Loader2 className="h-4 w-4 animate-spin text-brand-300" />
              <div className="w-56">
                <div className="flex items-center justify-between text-xs">
                  <span className="truncate font-medium">{(job as { stage?: string }).stage || "Working"}</span>
                  <span className="tabular-nums text-muted">{(job as { progress?: number }).progress ?? 0}%</span>
                </div>
                <ProgressBar value={Number((job as { progress?: number }).progress ?? 0)} className="mt-1" animated />
                <p className="mt-0.5 truncate text-[11px] text-muted">{(job as { message?: string }).message} {(job as { eta_seconds?: number | null }).eta_seconds != null ? `· ${formatEta((job as { eta_seconds?: number | null }).eta_seconds)}` : ""}</p>
              </div>
              <JobStateBadge state={String((job as { state: string }).state)} />
              <Button variant="ghost" size="icon" title="Cancel" onClick={() => cancel.mutate(String((job as { job_id?: string; id?: string }).job_id ?? (job as { id?: string }).id))}>
                <XCircle className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            p && (
              <Button variant="primary" loading={run.isPending} onClick={() => run.mutate()} title="Run every remaining stage and render">
                <Wand2 className="h-4 w-4" /> {p.pipeline?.render ? "Regenerate all" : "Generate video"}
              </Button>
            )
          )}
        </div>
      </div>

      <nav className="mb-6 flex gap-1 overflow-x-auto rounded-xl border border-line bg-panel p-1">
        {STEPS.map((s) => {
          const done = "key" in s && p?.pipeline?.[s.key];
          const active = current === s.id;
          return (
            <Link key={s.id} href={`/projects/${projectId}${s.href}`} className={cn("flex min-w-max flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition", active ? "bg-panel2 text-fg shadow" : "text-muted hover:text-fg")}>
              <span className={cn("grid h-5 w-5 place-items-center rounded-full border text-[10px]", done ? "border-emerald-500/60 bg-emerald-500/15 text-emerald-300" : "border-line")}>{done ? <Check className="h-3 w-3" /> : <s.icon className="h-3 w-3" />}</span>
              {s.label}
            </Link>
          );
        })}
      </nav>

      {p ? children(p) : <div className="space-y-3"><Skeleton className="h-24" /><Skeleton className="h-64" /></div>}
      <div className="h-10" />
      <Film className="hidden" />
    </div>
  );
}
