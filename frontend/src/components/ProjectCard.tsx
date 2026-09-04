"use client";
import Link from "next/link";
import { Film, Clock3, MoreHorizontal, Copy, Trash2, Play } from "lucide-react";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { ProjectSummary } from "@/types/api";
import { api } from "@/lib/api";
import { formatMinutes, formatRelative, cn } from "@/lib/utils";
import { ProgressBar, ProjectStatusBadge } from "@/components/ui";

export function ProjectCard({ project: p }: { project: ProjectSummary }) {
  const qc = useQueryClient();
  const [menu, setMenu] = useState(false);
  const del = useMutation({
    mutationFn: () => api.projects.remove(p.id),
    onSuccess: () => {
      toast.success("Project archived");
      void qc.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const dup = useMutation({
    mutationFn: () => api.projects.duplicate(p.id),
    onSuccess: () => {
      toast.success("Project duplicated");
      void qc.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const job = p.active_job;
  const href = p.status === "completed" ? `/projects/${p.id}/export` : p.status === "draft" ? `/projects/${p.id}` : `/projects/${p.id}`;
  return (
    <div className="card group relative overflow-hidden transition hover:border-brand-500/50">
      <Link href={href} className="block">
        <div className="relative aspect-video w-full overflow-hidden bg-panel2">
          {p.thumbnail_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={p.thumbnail_url} alt="" className="h-full w-full object-cover transition group-hover:scale-[1.02]" />
          ) : (
            <div className="grid h-full w-full place-items-center bg-[radial-gradient(ellipse_at_center,rgba(58,95,255,0.25),transparent_70%)] text-muted">
              <Film className="h-8 w-8" />
            </div>
          )}
          <div className="absolute left-2 top-2 flex gap-1">
            <ProjectStatusBadge status={p.status} className="backdrop-blur" />
          </div>
          <span className="absolute bottom-2 right-2 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[10px] text-white">{p.aspect_ratio} · {p.resolution}</span>
          {p.status === "completed" && (
            <span className="absolute inset-0 grid place-items-center opacity-0 transition group-hover:opacity-100">
              <span className="grid h-10 w-10 place-items-center rounded-full bg-white/90 text-black"><Play className="ml-0.5 h-5 w-5" /></span>
            </span>
          )}
        </div>
        <div className="p-3">
          <h3 className="truncate text-sm font-semibold">{p.title}</h3>
          <p className="mt-0.5 line-clamp-1 text-xs text-muted">{p.topic}</p>
          {job && !["COMPLETED", "FAILED", "CANCELLED"].includes(String(job.state)) ? (
            <div className="mt-2">
              <ProgressBar value={Number(job.progress ?? 0)} animated />
              <p className="mt-1 truncate text-[11px] text-brand-200">{job.stage || job.message} · {job.progress}%</p>
            </div>
          ) : (
            <div className="mt-2 flex items-center gap-3 text-[11px] text-muted">
              <span className="flex items-center gap-1"><Clock3 className="h-3 w-3" /> {p.estimated_duration_seconds ? formatMinutes(p.estimated_duration_seconds) : `${p.target_duration_minutes} min target`}</span>
              <span>· {formatRelative(p.updated_at)}</span>
            </div>
          )}
        </div>
      </Link>
      <button className={cn("absolute right-2 top-2 rounded-md bg-black/50 p-1 text-white opacity-0 transition group-hover:opacity-100", menu && "opacity-100")} onClick={() => setMenu((m) => !m)}>
        <MoreHorizontal className="h-4 w-4" />
      </button>
      {menu && (
        <div className="absolute right-2 top-9 z-10 w-40 rounded-lg border border-line bg-panel2 p-1 text-xs shadow-xl" onMouseLeave={() => setMenu(false)}>
          <button className="flex w-full items-center gap-2 rounded px-2 py-1.5 hover:bg-panel" onClick={() => dup.mutate()}><Copy className="h-3.5 w-3.5" /> Duplicate</button>
          <button className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-red-300 hover:bg-panel" onClick={() => confirm("Archive this project?") && del.mutate()}><Trash2 className="h-3.5 w-3.5" /> Archive</button>
        </div>
      )}
    </div>
  );
}
