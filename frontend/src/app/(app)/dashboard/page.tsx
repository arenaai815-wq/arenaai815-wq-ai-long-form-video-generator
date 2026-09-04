"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Film, PlusCircle, Coins, HardDrive, Clock3, CheckCircle2, ArrowRight, Activity } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/store/auth";
import { Button, Card, CardHeader, EmptyState, JobStateBadge, PageHeader, ProgressBar, ProjectStatusBadge, Skeleton, Stat } from "@/components/ui";
import { formatBytes, formatEta, formatMinutes, formatRelative } from "@/lib/utils";
import { ProjectCard } from "@/components/ProjectCard";

export default function DashboardPage() {
  const user = useAuth((s) => s.user);
  const stats = useQuery({ queryKey: ["projects", "stats"], queryFn: api.projects.stats });
  const recent = useQuery({ queryKey: ["projects", "recent"], queryFn: () => api.projects.list({ page_size: 6 }) });
  const drafts = useQuery({ queryKey: ["projects", "drafts"], queryFn: () => api.projects.list({ page_size: 5, status: "draft" }) });
  const completed = useQuery({ queryKey: ["projects", "completed"], queryFn: () => api.projects.list({ page_size: 5, status: "completed" }) });
  const jobs = useQuery({ queryKey: ["jobs", "active"], queryFn: () => api.jobs.list({ page_size: 8, active: true }), refetchInterval: 15_000 });
  const usage = useQuery({ queryKey: ["usage", "summary"], queryFn: () => api.usage.summary() });
  const storage = useQuery({ queryKey: ["storage"], queryFn: api.media.storage });

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title={`Good ${greeting()}, ${user?.full_name?.split(" ")[0] || "creator"}`}
        description="Your production line at a glance."
        actions={
          <Link href="/projects/new" className="btn-primary">
            <PlusCircle className="h-4 w-4" /> New project
          </Link>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Credits" value={user?.credits_balance ?? "…"} sub={usage.data ? `${usage.data.credits_used} used this month` : undefined} icon={<Coins className="h-5 w-5" />} />
        <Stat label="Videos completed" value={stats.data?.completed ?? "…"} sub={stats.data ? `${stats.data.total} projects total` : undefined} icon={<CheckCircle2 className="h-5 w-5" />} />
        <Stat label="Render minutes" value={usage.data ? usage.data.render_minutes.toFixed(1) : "…"} sub="this billing period" icon={<Clock3 className="h-5 w-5" />} />
        <Stat
          label="Storage"
          value={storage.data ? formatBytes(storage.data.used_bytes) : "…"}
          sub={storage.data ? `of ${formatBytes(storage.data.limit_bytes, 0)} · ${storage.data.asset_count} assets` : undefined}
          icon={<HardDrive className="h-5 w-5" />}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader
              title="Recent projects"
              description="Pick up where you left off."
              action={
                <Link href="/projects" className="btn-ghost text-xs">
                  All projects <ArrowRight className="h-3 w-3" />
                </Link>
              }
            />
            {recent.isLoading ? (
              <div className="grid gap-3 sm:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-40" />)}</div>
            ) : recent.data?.items.length ? (
              <div className="grid gap-3 sm:grid-cols-2">{recent.data.items.map((p) => <ProjectCard key={p.id} project={p} />)}</div>
            ) : (
              <EmptyState icon={<Film className="h-6 w-6" />} title="No projects yet" description="Create a project, give it a topic, and let the pipeline produce your first long-form video." action={<Link href="/projects/new" className="btn-primary">Create project</Link>} />
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Generation status" description="Live from the job queue." action={<Link href="/jobs" className="btn-ghost text-xs"><Activity className="h-3 w-3" /> Jobs</Link>} />
            {jobs.isLoading ? (
              <Skeleton className="h-16" />
            ) : jobs.data?.items.length ? (
              <ul className="space-y-3">
                {jobs.data.items.map((j) => (
                  <li key={j.id} className="text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <Link href={`/projects/${j.project_id}/export`} className="truncate font-medium hover:underline">{j.stage || j.job_type}</Link>
                      <JobStateBadge state={j.state} />
                    </div>
                    <ProgressBar value={j.progress} className="mt-1.5" animated />
                    <p className="mt-1 truncate text-xs text-muted">{j.message} {j.eta_seconds != null && <span>· {formatEta(j.eta_seconds)}</span>}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">Nothing running. Queue is idle.</p>
            )}
          </Card>

          <Card>
            <CardHeader title="Drafts" description="Projects waiting for generation." />
            {drafts.data?.items.length ? (
              <ul className="divide-y divide-line">
                {drafts.data.items.map((p) => (
                  <li key={p.id} className="flex items-center justify-between py-2 text-sm">
                    <Link href={`/projects/${p.id}`} className="truncate hover:underline">{p.title}</Link>
                    <span className="text-xs text-muted">{formatRelative(p.updated_at)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">No drafts.</p>
            )}
          </Card>

          <Card>
            <CardHeader title="Completed" description="Ready to download." />
            {completed.data?.items.length ? (
              <ul className="divide-y divide-line">
                {completed.data.items.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                    <Link href={`/projects/${p.id}/export`} className="truncate hover:underline">{p.title}</Link>
                    <span className="shrink-0 text-xs text-muted">{formatMinutes(p.estimated_duration_seconds)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">No finished videos yet.</p>
            )}
          </Card>

          {usage.data && (
            <Card>
              <CardHeader title="Usage this month" action={<Link href="/billing" className="btn-ghost text-xs">Details</Link>} />
              <ul className="space-y-1.5 text-xs">
                {Object.entries(usage.data.by_kind)
                  .filter(([, v]) => v.quantity > 0)
                  .map(([k, v]) => (
                    <li key={k} className="flex justify-between">
                      <span className="text-muted">{k.replace(/_/g, " ")}</span>
                      <span className="tabular-nums">{Number(v.quantity.toFixed(1))} {v.unit} · {v.credits} cr</span>
                    </li>
                  ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
      <div className="h-8" />
      <ProjectStatusLegend />
    </div>
  );
}

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
}

function ProjectStatusLegend() {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
      <span>Statuses:</span>
      {(["draft", "generating", "rendering", "completed", "failed"] as const).map((s) => (
        <ProjectStatusBadge key={s} status={s} />
      ))}
      <Button variant="ghost" size="sm" className="ml-auto" onClick={() => window.open("/api/v1/docs", "_blank")}>API docs</Button>
    </div>
  );
}
