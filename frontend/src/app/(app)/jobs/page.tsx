"use client";
import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Activity, Server, XCircle, RotateCcw, ScrollText, Cpu, Layers } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useUserStream } from "@/hooks/useJobStream";
import type { Job, ProgressEvent } from "@/types/api";
import { Alert, Button, Card, CardHeader, JobStateBadge, Modal, PageHeader, ProgressBar, Select, Stat } from "@/components/ui";
import { cn, formatDate, formatEta, formatRelative, titleCase } from "@/lib/utils";

export default function JobsPage() {
  const qc = useQueryClient();
  const [state, setState] = useState("");
  const [page, setPage] = useState(1);
  const [live, setLive] = useState<Record<string, ProgressEvent>>({});
  const [logsFor, setLogsFor] = useState<string | null>(null);
  const jobs = useQuery({ queryKey: ["jobs", "all", { state, page }], queryFn: () => api.jobs.list({ state: state || undefined, page, page_size: 25 }) });
  const workers = useQuery({ queryKey: ["workers"], queryFn: api.health.workers, refetchInterval: 15_000 });
  const queues = useQuery({ queryKey: ["queues"], queryFn: api.health.queues, refetchInterval: 15_000 });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health.api, refetchInterval: 30_000 });
  useUserStream({
    onEvent: (ev) => {
      setLive((m) => ({ ...m, [ev.job_id]: ev }));
      if (["COMPLETED", "FAILED", "CANCELLED"].includes(ev.state)) void qc.invalidateQueries({ queryKey: ["jobs", "all"] });
    },
  });
  const cancel = useMutation({ mutationFn: (id: string) => api.jobs.cancel(id), onSuccess: () => toast("Cancellation requested"), onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed") });
  const retry = useMutation({ mutationFn: (id: string) => api.jobs.retry(id), onSuccess: () => { toast.success("Job re-queued"); void qc.invalidateQueries({ queryKey: ["jobs", "all"] }); }, onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed") });
  const logs = useQuery({ queryKey: ["job-logs", logsFor], queryFn: () => api.jobs.logs(logsFor!), enabled: !!logsFor });

  const q = queues.data;
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Jobs & workers" description="Every generation and render job, plus the health of the worker fleet." />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Running" value={q?.processing ?? "…"} sub={q ? `${q.queued} queued` : undefined} icon={<Activity className="h-5 w-5" />} />
        <Stat label="Completed (24h)" value={q?.completed_24h ?? "…"} sub={q ? `${q.failed_24h} failed` : undefined} icon={<Layers className="h-5 w-5" />} />
        <Stat label="Workers online" value={q?.workers_online ?? "…"} sub={workers.data ? `${workers.data.reduce((a, w) => a + w.concurrency, 0)} total slots` : undefined} icon={<Server className="h-5 w-5" />} />
        <Stat label="API" value={health.data?.status === "ok" ? "Healthy" : health.isError ? "Down" : health.data?.status ?? "…"} sub={health.data?.version ? `v${health.data.version}` : undefined} icon={<Cpu className="h-5 w-5" />} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader title="Jobs" action={<Select className="w-44" value={state} onChange={(e) => { setState(e.target.value); setPage(1); }}><option value="">All states</option>{["QUEUED", "PROCESSING", "GENERATING_SCRIPT", "GENERATING_AUDIO", "GENERATING_VISUALS", "RENDERING", "COMPLETED", "FAILED", "CANCELLED"].map((s) => <option key={s}>{s}</option>)}</Select>} />
            {jobs.data?.items.length ? (
              <ul className="divide-y divide-line">
                {jobs.data.items.map((j) => <JobRow key={j.id} j={j} ev={live[j.id]} onCancel={() => cancel.mutate(j.id)} onRetry={() => retry.mutate(j.id)} onLogs={() => setLogsFor(j.id)} />)}
              </ul>
            ) : (
              <p className="text-sm text-muted">{jobs.isLoading ? "Loading…" : "No jobs."}</p>
            )}
            {jobs.data && jobs.data.total > jobs.data.page_size && (
              <div className="mt-4 flex items-center justify-center gap-2 text-sm">
                <Button size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
                <span className="text-muted">Page {page} of {Math.ceil(jobs.data.total / jobs.data.page_size)}</span>
                <Button size="sm" disabled={page * jobs.data.page_size >= jobs.data.total} onClick={() => setPage(page + 1)}>Next</Button>
              </div>
            )}
          </Card>
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Workers" description="Heartbeats from Celery workers." />
            {workers.data?.length ? (
              <ul className="space-y-2">
                {workers.data.map((w) => (
                  <li key={w.worker_id} className="rounded-lg border border-line p-2 text-xs">
                    <div className="flex items-center justify-between"><span className="font-mono">{w.worker_id}</span><span className={cn("badge", w.healthy ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : "border-red-500/40 bg-red-500/10 text-red-300")}>{w.healthy ? "healthy" : "stale"}</span></div>
                    <p className="mt-1 text-muted">queues: {w.queues.join(", ")} · {w.active_tasks}/{w.concurrency} busy</p>
                    <p className="text-muted">{w.processed_total} processed · {w.failed_total} failed · heartbeat {formatRelative(w.last_heartbeat_at)}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <Alert tone="warning">No workers online. Start one with <code>celery -A workers.celery_app worker</code> — jobs will wait in the queue until then.</Alert>
            )}
          </Card>
          <Card>
            <CardHeader title="Queue depth" />
            <ul className="space-y-2 text-xs">
              {q && Object.entries(q.queue_depths).map(([name, depth]) => (
                <li key={name}>
                  <div className="flex justify-between"><span className="font-mono">{name}</span><span>{depth}</span></div>
                  <ProgressBar value={Math.min(100, depth * 10)} className="mt-1" />
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
      <Modal open={!!logsFor} onClose={() => setLogsFor(null)} title="Job logs" size="lg">
        {logs.data ? (
          <div className="space-y-2">
            {logs.data.error && <Alert tone="error" title="Error">{logs.data.error}</Alert>}
            <pre className="max-h-[50vh] overflow-auto rounded-lg bg-black/40 p-3 font-mono text-[11px] leading-relaxed">{logs.data.logs.length ? logs.data.logs.map((l, i) => <div key={i} className={cn(l.level === "error" && "text-red-300", l.level === "warning" && "text-amber-300")}>{formatDate(l.ts)} [{l.level}] {l.message}</div>) : "No log entries."}</pre>
          </div>
        ) : <p className="text-sm text-muted">Loading…</p>}
      </Modal>
    </div>
  );
}

function JobRow({ j, ev, onCancel, onRetry, onLogs }: { j: Job; ev?: ProgressEvent; onCancel: () => void; onRetry: () => void; onLogs: () => void }) {
  const state = ev?.state ?? j.state;
  const progress = ev?.progress ?? j.progress;
  const terminal = ["COMPLETED", "FAILED", "CANCELLED"].includes(state);
  return (
    <li className="py-3">
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-sm">
            <Link href={`/projects/${j.project_id}`} className="font-medium hover:underline">{titleCase(j.job_type)}</Link>
            <JobStateBadge state={state} />
            <span className="text-xs text-muted">{j.kind}</span>
          </div>
          <p className="truncate text-xs text-muted">{ev?.message ?? j.error ?? j.message} {ev?.eta_seconds != null && `· ${formatEta(ev.eta_seconds)}`}</p>
          <p className="text-[10px] text-muted">{formatRelative(j.created_at)} · attempt {j.attempt}/{j.max_attempts} · {j.credits_charged} cr · <span className="font-mono">{j.id.slice(0, 8)}</span></p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button variant="ghost" size="icon" title="Logs" onClick={onLogs}><ScrollText className="h-4 w-4" /></Button>
          {!terminal && <Button variant="ghost" size="icon" title="Cancel" onClick={onCancel}><XCircle className="h-4 w-4" /></Button>}
          {(state === "FAILED" || state === "CANCELLED") && <Button variant="ghost" size="icon" title="Retry" onClick={onRetry}><RotateCcw className="h-4 w-4" /></Button>}
        </div>
      </div>
      {!terminal && <ProgressBar value={progress} className="mt-2" animated />}
    </li>
  );
}
