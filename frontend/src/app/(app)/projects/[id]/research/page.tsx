"use client";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { BookOpenText, Plus, Trash2, Sparkles, Save, CheckCircle2, ExternalLink, ArrowRight, Link as LinkIcon } from "lucide-react";
import Link from "next/link";
import { ProjectShell } from "@/components/project/ProjectShell";
import { api, ApiError } from "@/lib/api";
import type { ProjectDetail, Research, ResearchSection } from "@/types/api";
import { Alert, Button, Card, CardHeader, EmptyState, Field, Input, Modal, Select, Textarea } from "@/components/ui";
import { cn, formatRelative } from "@/lib/utils";

export default function ResearchPage({ params }: { params: { id: string } }) {
  const id = params.id;
  return <ProjectShell projectId={id}>{(p) => <ResearchView p={p} />}</ProjectShell>;
}

function ResearchView({ p }: { p: ProjectDetail }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["research", p.id], queryFn: () => api.research.get(p.id), retry: false });
  const [draft, setDraft] = useState<Research | null>(null);
  const [dirty, setDirty] = useState(false);
  const [genOpen, setGenOpen] = useState(false);
  const [genOpts, setGenOpts] = useState({ section_count: 6, depth: "standard", focus: "" });
  useEffect(() => {
    if (q.data && !dirty) setDraft(q.data);
  }, [q.data, dirty]);

  const generate = useMutation({
    mutationFn: () => api.research.generate(p.id, { section_count: genOpts.section_count, depth: genOpts.depth, focus: genOpts.focus || undefined }),
    onSuccess: () => {
      toast.success("Research started");
      setGenOpen(false);
      setDirty(false);
      void qc.invalidateQueries({ queryKey: ["project", p.id] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed to start research"),
  });
  const save = useMutation({
    mutationFn: (approve?: boolean) =>
      api.research.update(p.id, {
        summary: draft!.summary,
        sections: draft!.sections,
        key_facts: draft!.key_facts,
        statistics: draft!.statistics,
        sources: draft!.sources,
        suggested_angles: draft!.suggested_angles,
        keywords: draft!.keywords,
        approved: approve,
      }),
    onSuccess: (data, approve) => {
      setDraft(data);
      setDirty(false);
      toast.success(approve ? "Research approved — ready for scripting" : "Research saved");
      void qc.invalidateQueries({ queryKey: ["research", p.id] });
      void qc.invalidateQueries({ queryKey: ["project", p.id] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Save failed"),
  });

  const running = p.active_job && !["COMPLETED", "FAILED", "CANCELLED"].includes(String(p.active_job.state));
  const update = (fn: (r: Research) => Research) => {
    setDraft((d) => (d ? fn(d) : d));
    setDirty(true);
  };
  const updateSection = (i: number, fn: (s: ResearchSection) => ResearchSection) => update((r) => ({ ...r, sections: r.sections.map((s, j) => (j === i ? fn(s) : s)) }));

  const genModal = (
    <Modal open={genOpen} onClose={() => setGenOpen(false)} title="Generate research" footer={<><Button onClick={() => setGenOpen(false)}>Cancel</Button><Button variant="primary" loading={generate.isPending} onClick={() => generate.mutate()}><Sparkles className="h-4 w-4" /> Generate</Button></>}>
      <div className="space-y-4">
        <p className="text-sm text-muted">The research agent organises facts, statistics, sources and narrative hooks into sections. Costs 5 credits.</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Sections"><Input type="number" min={3} max={14} value={genOpts.section_count} onChange={(e) => setGenOpts({ ...genOpts, section_count: Number(e.target.value) })} /></Field>
          <Field label="Depth"><Select value={genOpts.depth} onChange={(e) => setGenOpts({ ...genOpts, depth: e.target.value })}><option value="quick">Quick</option><option value="standard">Standard</option><option value="deep">Deep</option></Select></Field>
        </div>
        <Field label="Focus (optional)"><Textarea rows={2} value={genOpts.focus} onChange={(e) => setGenOpts({ ...genOpts, focus: e.target.value })} placeholder="Emphasise the climate science; include at least three dated events." /></Field>
      </div>
    </Modal>
  );

  if (q.isLoading) return <Card><div className="skeleton h-40" /></Card>;
  if (!draft || (!draft.sections?.length && !draft.summary)) {
    return (
      <>
        <EmptyState icon={<BookOpenText className="h-6 w-6" />} title={running ? "Research in progress…" : "No research yet"} description={running ? "The research agent is gathering facts, statistics and sources for your topic." : "Run the research agent to build a fact base for the script."} action={!running && <Button variant="primary" onClick={() => setGenOpen(true)}><Sparkles className="h-4 w-4" /> Generate research</Button>} />
        {genModal}
      </>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs text-muted">
          {draft.provider && <span>Generated by <span className="font-mono">{draft.provider}{draft.model ? ` / ${draft.model}` : ""}</span> · </span>}
          updated {formatRelative(draft.updated_at)}
          {draft.approved_at && <span className="ml-2 badge border-emerald-500/40 bg-emerald-500/10 text-emerald-300"><CheckCircle2 className="h-3 w-3" /> approved</span>}
          {dirty && <span className="ml-2 text-amber-300">unsaved changes</span>}
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => setGenOpen(true)} disabled={!!running}><Sparkles className="h-4 w-4" /> Regenerate</Button>
          <Button disabled={!dirty} loading={save.isPending && save.variables === undefined} onClick={() => save.mutate(undefined)}><Save className="h-4 w-4" /> Save</Button>
          <Button variant="primary" loading={save.isPending && save.variables === true} onClick={() => save.mutate(true)}><CheckCircle2 className="h-4 w-4" /> Approve</Button>
          <Link href={`/projects/${p.id}/script`} className="btn-secondary">Script <ArrowRight className="h-4 w-4" /></Link>
        </div>
      </div>

      {running && <Alert tone="info">A generation job is running. New research will replace this content when it finishes.</Alert>}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader title="Summary" description="One-paragraph framing the writer will follow." />
            <Textarea rows={4} value={draft.summary ?? ""} onChange={(e) => update((r) => ({ ...r, summary: e.target.value }))} />
          </Card>

          {draft.sections.map((s, i) => (
            <Card key={i}>
              <div className="mb-3 flex items-center gap-2">
                <span className="font-mono text-xs text-muted">{String(i + 1).padStart(2, "0")}</span>
                <Input className="font-semibold" value={s.title} onChange={(e) => updateSection(i, (x) => ({ ...x, title: e.target.value }))} />
                <Button variant="ghost" size="icon" title="Remove section" onClick={() => update((r) => ({ ...r, sections: r.sections.filter((_, j) => j !== i) }))}><Trash2 className="h-4 w-4" /></Button>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <ListEditor label="Key points" items={s.key_points} onChange={(v) => updateSection(i, (x) => ({ ...x, key_points: v }))} />
                <ListEditor label="Facts" items={s.facts} onChange={(v) => updateSection(i, (x) => ({ ...x, facts: v }))} />
                <StatsEditor items={s.statistics} onChange={(v) => updateSection(i, (x) => ({ ...x, statistics: v }))} />
                <ListEditor label="Narrative hooks" items={s.narrative_hooks} onChange={(v) => updateSection(i, (x) => ({ ...x, narrative_hooks: v }))} />
              </div>
              {s.sources?.length > 0 && (
                <div className="mt-3">
                  <p className="label">Sources</p>
                  <ul className="space-y-1 text-xs">
                    {s.sources.map((src, k) => (
                      <li key={k} className="flex items-center gap-2 text-muted">
                        <LinkIcon className="h-3 w-3" />
                        {src.url ? <a href={src.url} target="_blank" rel="noreferrer" className="hover:text-fg hover:underline">{src.title}</a> : src.title}
                        {src.note && <span>— {src.note}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          ))}
          <Button onClick={() => update((r) => ({ ...r, sections: [...r.sections, { title: "New section", key_points: [], facts: [], statistics: [], sources: [], narrative_hooks: [] }] }))}><Plus className="h-4 w-4" /> Add section</Button>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Key facts" description="Cross-section highlights." />
            <ListEditor items={draft.key_facts} onChange={(v) => update((r) => ({ ...r, key_facts: v }))} />
          </Card>
          <Card>
            <CardHeader title="Statistics" />
            <StatsEditor items={draft.statistics} onChange={(v) => update((r) => ({ ...r, statistics: v }))} />
          </Card>
          <Card>
            <CardHeader title="Suggested angles" />
            <ListEditor items={draft.suggested_angles} onChange={(v) => update((r) => ({ ...r, suggested_angles: v }))} />
          </Card>
          <Card>
            <CardHeader title="Keywords" />
            <Input value={draft.keywords.join(", ")} onChange={(e) => update((r) => ({ ...r, keywords: e.target.value.split(",").map((k) => k.trim()).filter(Boolean) }))} placeholder="comma, separated, keywords" />
          </Card>
          <Card>
            <CardHeader title="Sources" description={`${draft.sources.length} references`} />
            <ul className="space-y-2 text-xs">
              {draft.sources.map((s, i) => (
                <li key={i} className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{s.title}</p>
                    {s.note && <p className="truncate text-muted">{s.note}</p>}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {s.url && <a className="btn-ghost h-6 w-6 p-0" href={s.url} target="_blank" rel="noreferrer"><ExternalLink className="h-3 w-3" /></a>}
                    <button className="btn-ghost h-6 w-6 p-0" onClick={() => update((r) => ({ ...r, sources: r.sources.filter((_, j) => j !== i) }))}><Trash2 className="h-3 w-3" /></button>
                  </div>
                </li>
              ))}
            </ul>
            <SourceAdder onAdd={(s) => update((r) => ({ ...r, sources: [...r.sources, s] }))} />
          </Card>
        </div>
      </div>
      {genModal}
    </div>
  );
}

function ListEditor({ label, items, onChange }: { label?: string; items: string[]; onChange: (v: string[]) => void }) {
  return (
    <div>
      {label && <p className="label">{label}</p>}
      <ul className="space-y-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex items-start gap-1">
            <Textarea rows={1} className="min-h-0 py-1.5 text-xs" value={it} onChange={(e) => onChange(items.map((x, j) => (j === i ? e.target.value : x)))} />
            <button className="btn-ghost mt-1 h-6 w-6 shrink-0 p-0" onClick={() => onChange(items.filter((_, j) => j !== i))}><Trash2 className="h-3 w-3" /></button>
          </li>
        ))}
      </ul>
      <button className="mt-1.5 flex items-center gap-1 text-xs text-brand-300 hover:underline" onClick={() => onChange([...items, ""])}><Plus className="h-3 w-3" /> Add</button>
    </div>
  );
}

function StatsEditor({ items, onChange }: { items: { value: string; context: string; source?: string | null }[]; onChange: (v: { value: string; context: string; source?: string | null }[]) => void }) {
  return (
    <div>
      <p className="label">Statistics</p>
      <ul className="space-y-1.5">
        {items.map((st, i) => (
          <li key={i} className="flex items-start gap-1">
            <Input className={cn("w-24 shrink-0 py-1.5 font-mono text-xs")} value={st.value} placeholder="9.2M km²" onChange={(e) => onChange(items.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
            <Input className="py-1.5 text-xs" value={st.context} placeholder="context" onChange={(e) => onChange(items.map((x, j) => (j === i ? { ...x, context: e.target.value } : x)))} />
            <button className="btn-ghost mt-1 h-6 w-6 shrink-0 p-0" onClick={() => onChange(items.filter((_, j) => j !== i))}><Trash2 className="h-3 w-3" /></button>
          </li>
        ))}
      </ul>
      <button className="mt-1.5 flex items-center gap-1 text-xs text-brand-300 hover:underline" onClick={() => onChange([...items, { value: "", context: "" }])}><Plus className="h-3 w-3" /> Add statistic</button>
    </div>
  );
}

function SourceAdder({ onAdd }: { onAdd: (s: { title: string; url?: string | null; note?: string | null }) => void }) {
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  return (
    <div className="mt-3 flex gap-1">
      <Input className="py-1.5 text-xs" placeholder="Source title" value={title} onChange={(e) => setTitle(e.target.value)} />
      <Input className="py-1.5 text-xs" placeholder="https://" value={url} onChange={(e) => setUrl(e.target.value)} />
      <Button size="sm" disabled={!title} onClick={() => { onAdd({ title, url: url || null }); setTitle(""); setUrl(""); }}><Plus className="h-3.5 w-3.5" /></Button>
    </div>
  );
}
