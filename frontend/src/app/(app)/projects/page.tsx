"use client";
import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { PlusCircle, Search, Film } from "lucide-react";
import { api } from "@/lib/api";
import { Button, EmptyState, Input, PageHeader, Select, Skeleton } from "@/components/ui";
import { ProjectCard } from "@/components/ProjectCard";

const statuses = ["", "draft", "researching", "scripting", "storyboarding", "generating", "rendering", "completed", "failed"];

export default function ProjectsPage() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [archived, setArchived] = useState(false);
  const projects = useQuery({ queryKey: ["projects", { q, status, page, archived }], queryFn: () => api.projects.list({ q, status: status || undefined, page, page_size: 12, include_archived: archived }) });
  const pages = projects.data ? Math.max(1, Math.ceil(projects.data.total / projects.data.page_size)) : 1;
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Projects" description={projects.data ? `${projects.data.total} project${projects.data.total === 1 ? "" : "s"}` : undefined} actions={<Link href="/projects/new" className="btn-primary"><PlusCircle className="h-4 w-4" /> New project</Link>} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-72">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted" />
          <Input className="pl-8" placeholder="Search title or topic…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        </div>
        <Select className="w-44" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          {statuses.map((s) => <option key={s} value={s}>{s ? s[0].toUpperCase() + s.slice(1) : "All statuses"}</option>)}
        </Select>
        <label className="flex items-center gap-2 text-xs text-muted"><input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} /> Include archived</label>
      </div>
      {projects.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-56" />)}</div>
      ) : projects.data?.items.length ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{projects.data.items.map((p) => <ProjectCard key={p.id} project={p} />)}</div>
          {pages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-2 text-sm">
              <Button size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <span className="text-muted">Page {page} of {pages}</span>
              <Button size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          )}
        </>
      ) : (
        <EmptyState icon={<Film className="h-6 w-6" />} title={q || status ? "No matching projects" : "No projects yet"} description="Create a project to start the research → script → storyboard → render pipeline." action={<Link href="/projects/new" className="btn-primary">Create project</Link>} />
      )}
    </div>
  );
}
