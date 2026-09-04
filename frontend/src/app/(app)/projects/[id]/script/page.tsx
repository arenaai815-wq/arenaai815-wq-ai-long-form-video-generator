"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileText, Sparkles, RefreshCw, Lock, Unlock, Trash2, Plus, ChevronUp, ChevronDown, ArrowRight, History, Clock3, Type, Save } from "lucide-react";
import { ProjectShell } from "@/components/project/ProjectShell";
import { api, ApiError } from "@/lib/api";
import type { ProjectDetail, Script, ScriptSection } from "@/types/api";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, Field, Input, Modal, ProgressBar, Select, Textarea } from "@/components/ui";
import { cn, formatDuration, wordCount } from "@/lib/utils";

const KINDS = ["hook", "intro", "body", "story", "transition", "conclusion", "cta"];
const KIND_COLORS: Record<string, string> = { hook: "border-pink-500/40 bg-pink-500/10 text-pink-200", intro: "border-sky-500/40 bg-sky-500/10 text-sky-200", body: "border-line bg-panel2 text-muted", story: "border-violet-500/40 bg-violet-500/10 text-violet-200", transition: "border-zinc-500/40 bg-zinc-500/10 text-zinc-300", conclusion: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200", cta: "border-amber-500/40 bg-amber-500/10 text-amber-200" };

export default function ScriptPage({ params }: { params: { id: string } }) {
  const id = params.id;
  return <ProjectShell projectId={id}>{(p) => <ScriptEditor p={p} />}</ProjectShell>;
}

function ScriptEditor({ p }: { p: ProjectDetail }) {
  const qc = useQueryClient();
  const script = useQuery({ queryKey: ["script", p.id], queryFn: () => api.script.get(p.id), retry: false });
  const stats = useQuery({ queryKey: ["script", p.id, "stats"], queryFn: () => api.script.stats(p.id), enabled: !!script.data, retry: false });
  const [genOpen, setGenOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [gen, setGen] = useState({ target_duration_minutes: p.target_duration_minutes, tone: p.tone, instructions: "", words_per_minute: p.settings?.words_per_minute ?? 150 });
  const [selected, setSelected] = useState<string | null>(null);
  const running = p.active_job && !["COMPLETED", "FAILED", "CANCELLED"].includes(String(p.active_job.state));
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["script", p.id] });
    void qc.invalidateQueries({ queryKey: ["project", p.id] });
  };
  const generate = useMutation({
    mutationFn: () => api.script.generate(p.id, { ...gen, instructions: gen.instructions || undefined }),
    onSuccess: () => {
      toast.success("Script generation started");
      setGenOpen(false);
      invalidate();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not start"),
  });
  const addSection = useMutation({
    mutationFn: (after: string | null) => api.script.addSection(p.id, { heading: "New section", kind: "body", content: "", after_section_id: after }),
    onSuccess: (s) => {
      qc.setQueryData(["script", p.id], s);
      invalidate();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not add section"),
  });
  const reorder = useMutation({
    mutationFn: (ids: string[]) => api.script.reorder(p.id, ids),
    onSuccess: (s) => qc.setQueryData(["script", p.id], s),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not reorder"),
  });
  const move = (idx: number, dir: -1 | 1) => {
    const ids = (script.data?.sections ?? []).map((s) => s.id);
    const j = idx + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[idx], ids[j]] = [ids[j], ids[idx]];
    reorder.mutate(ids);
  };

  const s = script.data;
  const total = useMemo(() => (s ? s.sections.reduce((a, x) => a + x.word_count, 0) : 0), [s]);
  const targetSec = (s?.target_duration_minutes ?? p.target_duration_minutes) * 60;
  const estSec = s ? (total / (s.words_per_minute || 150)) * 60 : 0;
  const pct = targetSec ? Math.min(100, (estSec / targetSec) * 100) : 0;

  const genModal = (
    <Modal open={genOpen} onClose={() => setGenOpen(false)} title={s ? "Regenerate script" : "Generate script"} footer={<><Button onClick={() => setGenOpen(false)}>Cancel</Button><Button variant="primary" loading={generate.isPending} onClick={() => generate.mutate()}><Sparkles className="h-4 w-4" /> Generate</Button></>}>
      <div className="space-y-4">
        {s && <Alert tone="warning">A new version will be created; the current version stays available in history. Locked sections are preserved.</Alert>}
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Length (minutes)">
            <Select value={gen.target_duration_minutes} onChange={(e) => setGen({ ...gen, target_duration_minutes: Number(e.target.value) })}>{[1, 2, 3, 5, 8, 10, 15, 20, 30, 45, 60, 90, 120].map((m) => <option key={m} value={m}>{m} min</option>)}</Select>
          </Field>
          <Field label="Tone"><Input value={gen.tone} onChange={(e) => setGen({ ...gen, tone: e.target.value })} /></Field>
          <Field label="Words / minute"><Input type="number" min={90} max={220} value={gen.words_per_minute} onChange={(e) => setGen({ ...gen, words_per_minute: Number(e.target.value) })} /></Field>
        </div>
        <Field label="Instructions (optional)"><Textarea rows={3} value={gen.instructions} onChange={(e) => setGen({ ...gen, instructions: e.target.value })} placeholder="Open with a cold-open mystery; add a mid-roll recap; end with a question for the comments." /></Field>
        <p className="text-xs text-muted">≈ {(gen.target_duration_minutes * gen.words_per_minute).toLocaleString()} words · costs {2 * gen.target_duration_minutes} credits</p>
      </div>
    </Modal>
  );

  if (script.isLoading) return <Card><div className="skeleton h-40" /></Card>;
  if (!s || !s.sections.length) {
    return (
      <>
        <EmptyState icon={<FileText className="h-6 w-6" />} title={running ? "Script is being written…" : "No script yet"} description={running ? "Sections will appear here as soon as the writer finishes." : p.pipeline?.research ? "Generate a script from the approved research." : "Tip: run research first for a fact-grounded script — or generate directly from the topic."} action={!running && <Button variant="primary" onClick={() => setGenOpen(true)}><Sparkles className="h-4 w-4" /> Generate script</Button>} />
        {genModal}
      </>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-4">
      <div className="space-y-4 lg:col-span-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-muted">
            <Badge>v{s.version}</Badge>
            {s.provider && <span className="font-mono">{s.provider}{s.model ? ` / ${s.model}` : ""}</span>}
            {running && <span className="text-brand-200">generation running…</span>}
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={() => setHistoryOpen(true)}><History className="h-3.5 w-3.5" /> Versions</Button>
            <Button size="sm" onClick={() => setGenOpen(true)} disabled={!!running}><Sparkles className="h-3.5 w-3.5" /> Regenerate</Button>
            <Link href={`/projects/${p.id}/storyboard`} className="btn-primary px-3 py-1.5 text-xs">Storyboard <ArrowRight className="h-3.5 w-3.5" /></Link>
          </div>
        </div>

        <TitleHook p={p} s={s} />

        {s.sections.map((sec, i) => (
          <SectionCard key={sec.id} p={p} sec={sec} index={i} count={s.sections.length} selected={selected === sec.id} onSelect={() => setSelected(sec.id)} onMove={(d) => move(i, d)} onAddAfter={() => addSection.mutate(sec.id)} running={!!running} />
        ))}
        <Button onClick={() => addSection.mutate(null)}><Plus className="h-4 w-4" /> Add section at end</Button>
      </div>

      <div className="space-y-4">
        <Card className="sticky top-4">
          <CardHeader title="Runtime" description="Estimated from narration speed." />
          <div className="flex items-end justify-between">
            <span className="text-2xl font-semibold tabular-nums">{formatDuration(estSec)}</span>
            <span className="mb-1 text-xs text-muted">target {formatDuration(targetSec)}</span>
          </div>
          <ProgressBar value={pct} className="mt-2" tone={Math.abs(estSec - targetSec) / targetSec > 0.25 ? "red" : "green"} />
          <p className="mt-1 text-xs text-muted">{estSec < targetSec ? `${formatDuration(targetSec - estSec)} short` : `${formatDuration(estSec - targetSec)} over`} · {s.words_per_minute} wpm</p>
          <dl className="mt-4 grid grid-cols-2 gap-2 text-xs">
            <dt className="text-muted flex items-center gap-1"><Type className="h-3 w-3" /> Words</dt><dd className="text-right tabular-nums">{total.toLocaleString()}</dd>
            <dt className="text-muted flex items-center gap-1"><FileText className="h-3 w-3" /> Sections</dt><dd className="text-right tabular-nums">{s.sections.length}</dd>
            <dt className="text-muted flex items-center gap-1"><Clock3 className="h-3 w-3" /> Avg section</dt><dd className="text-right tabular-nums">{formatDuration(estSec / Math.max(1, s.sections.length))}</dd>
            {stats.data && <><dt className="text-muted">Δ target</dt><dd className="text-right tabular-nums">{stats.data.delta_seconds > 0 ? "+" : ""}{Math.round(stats.data.delta_seconds)}s</dd></>}
          </dl>
          <div className="mt-4">
            <p className="label">Outline</p>
            <ol className="space-y-1 text-xs">
              {s.sections.map((sec, i) => (
                <li key={sec.id}>
                  <button className={cn("flex w-full items-center gap-2 rounded px-1.5 py-1 text-left hover:bg-panel2", selected === sec.id && "bg-panel2")} onClick={() => { setSelected(sec.id); document.getElementById(`sec-${sec.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }); }}>
                    <span className="font-mono text-muted">{i + 1}</span>
                    <span className="truncate">{sec.heading}</span>
                    <span className="ml-auto shrink-0 text-muted">{formatDuration(sec.estimated_duration_seconds)}</span>
                  </button>
                </li>
              ))}
            </ol>
          </div>
        </Card>
      </div>
      {genModal}
      <VersionsModal p={p} open={historyOpen} onClose={() => setHistoryOpen(false)} current={s.version} />
    </div>
  );
}

function TitleHook({ p, s }: { p: ProjectDetail; s: Script }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState(s.title ?? "");
  const [hook, setHook] = useState(s.hook ?? "");
  useEffect(() => {
    setTitle(s.title ?? "");
    setHook(s.hook ?? "");
  }, [s.title, s.hook]);
  const save = useMutation({
    mutationFn: () => api.script.update(p.id, { title, hook }),
    onSuccess: (d) => qc.setQueryData(["script", p.id], d),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Save failed"),
  });
  const dirty = title !== (s.title ?? "") || hook !== (s.hook ?? "");
  return (
    <Card>
      <div className="grid gap-3 sm:grid-cols-[1fr_2fr]">
        <Field label="Working title"><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
        <Field label="One-line hook" hint="Shown on the intro card and used to guide the opening."><Input value={hook} onChange={(e) => setHook(e.target.value)} /></Field>
      </div>
      {dirty && <div className="mt-2 flex justify-end"><Button size="sm" variant="primary" loading={save.isPending} onClick={() => save.mutate()}><Save className="h-3.5 w-3.5" /> Save</Button></div>}
    </Card>
  );
}

function SectionCard({ p, sec, index, count, selected, onSelect, onMove, onAddAfter, running }: { p: ProjectDetail; sec: ScriptSection; index: number; count: number; selected: boolean; onSelect: () => void; onMove: (d: -1 | 1) => void; onAddAfter: () => void; running: boolean }) {
  const qc = useQueryClient();
  const [heading, setHeading] = useState(sec.heading);
  const [content, setContent] = useState(sec.content);
  const [kind, setKind] = useState(sec.kind);
  const [regenOpen, setRegenOpen] = useState(false);
  const [instructions, setInstructions] = useState("");
  const [regenJob, setRegenJob] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    setHeading(sec.heading);
    setContent(sec.content);
    setKind(sec.kind);
  }, [sec.heading, sec.content, sec.kind, sec.updated_at]);

  const save = useMutation({
    mutationFn: (body: { heading?: string; content?: string; kind?: string; is_locked?: boolean }) => api.script.updateSection(p.id, sec.id, body),
    onSuccess: (d) => {
      qc.setQueryData(["script", p.id], d);
      void qc.invalidateQueries({ queryKey: ["script", p.id, "stats"] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Save failed"),
  });
  const del = useMutation({
    mutationFn: () => api.script.deleteSection(p.id, sec.id),
    onSuccess: (d) => qc.setQueryData(["script", p.id], d),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Delete failed"),
  });
  const regen = useMutation({
    mutationFn: () => api.script.regenerateSection(p.id, sec.id, { instructions: instructions || undefined }),
    onSuccess: (job) => {
      setRegenOpen(false);
      setRegenJob(job.id);
      toast.success("Rewriting section…");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not regenerate"),
  });
  useEffect(() => {
    if (!regenJob) return;
    const id = setInterval(async () => {
      const j = await api.jobs.get(regenJob);
      if (["COMPLETED", "FAILED", "CANCELLED"].includes(j.state)) {
        clearInterval(id);
        setRegenJob(null);
        void qc.invalidateQueries({ queryKey: ["script", p.id] });
        if (j.state === "FAILED") toast.error(j.error || "Section regeneration failed");
      }
    }, 2000);
    return () => clearInterval(id);
  }, [regenJob, p.id, qc]);

  const dirty = heading !== sec.heading || content !== sec.content || kind !== sec.kind;
  const scheduleSave = (next: { heading?: string; content?: string; kind?: string }) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => save.mutate(next), 900);
  };
  const words = wordCount(content);
  const est = (words / 150) * 60;

  return (
    <Card id={`sec-${sec.id}`} className={cn("transition", selected && "border-brand-500/60", regenJob && "opacity-70")} onClick={onSelect}>
      <div className="mb-2 flex items-center gap-2">
        <span className="font-mono text-xs text-muted">{index + 1}</span>
        <select value={kind} onChange={(e) => { setKind(e.target.value); save.mutate({ kind: e.target.value }); }} className={cn("badge cursor-pointer appearance-none bg-transparent outline-none", KIND_COLORS[kind] || KIND_COLORS.body)}>
          {KINDS.map((k) => <option key={k} value={k} className="bg-panel text-fg">{k}</option>)}
        </select>
        <Input className="border-transparent bg-transparent px-1 py-1 font-semibold hover:border-line" value={heading} onChange={(e) => { setHeading(e.target.value); scheduleSave({ heading: e.target.value }); }} disabled={sec.is_locked} />
        <div className="ml-auto flex shrink-0 items-center gap-0.5">
          <Button variant="ghost" size="icon" title="Move up" disabled={index === 0} onClick={(e) => { e.stopPropagation(); onMove(-1); }}><ChevronUp className="h-4 w-4" /></Button>
          <Button variant="ghost" size="icon" title="Move down" disabled={index === count - 1} onClick={(e) => { e.stopPropagation(); onMove(1); }}><ChevronDown className="h-4 w-4" /></Button>
          <Button variant="ghost" size="icon" title={sec.is_locked ? "Unlock (allow regeneration)" : "Lock (protect from regeneration)"} onClick={(e) => { e.stopPropagation(); save.mutate({ is_locked: !sec.is_locked }); }}>{sec.is_locked ? <Lock className="h-4 w-4 text-amber-300" /> : <Unlock className="h-4 w-4" />}</Button>
          <Button variant="ghost" size="icon" title="Rewrite this section with AI" disabled={sec.is_locked || running || !!regenJob} onClick={(e) => { e.stopPropagation(); setRegenOpen(true); }}><RefreshCw className={cn("h-4 w-4", regenJob && "animate-spin")} /></Button>
          <Button variant="ghost" size="icon" title="Delete section" onClick={(e) => { e.stopPropagation(); if (confirm("Delete this section?")) del.mutate(); }}><Trash2 className="h-4 w-4" /></Button>
        </div>
      </div>
      <Textarea rows={Math.min(18, Math.max(4, Math.ceil(content.length / 110)))} className="border-transparent bg-transparent text-[15px] leading-7 hover:border-line focus:bg-panel2" value={content} disabled={sec.is_locked} onChange={(e) => { setContent(e.target.value); scheduleSave({ content: e.target.value }); }} placeholder="Narration text…" />
      <div className="mt-2 flex items-center justify-between text-[11px] text-muted">
        <span>{words} words · ≈ {formatDuration(est)} {sec.regeneration_count > 0 && `· rewritten ${sec.regeneration_count}×`} {dirty && <span className="text-amber-300">· saving…</span>}</span>
        <button className="flex items-center gap-1 hover:text-fg" onClick={(e) => { e.stopPropagation(); onAddAfter(); }}><Plus className="h-3 w-3" /> Insert section after</button>
      </div>
      <Modal open={regenOpen} onClose={() => setRegenOpen(false)} title={`Rewrite “${sec.heading}”`} footer={<><Button onClick={() => setRegenOpen(false)}>Cancel</Button><Button variant="primary" loading={regen.isPending} onClick={() => regen.mutate()}><RefreshCw className="h-4 w-4" /> Rewrite</Button></>}>
        <Field label="Instructions" hint="Only this section changes; the rest of the script stays as is."><Textarea rows={3} value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="Make it punchier and add a concrete example." /></Field>
      </Modal>
    </Card>
  );
}

function VersionsModal({ p, open, onClose, current }: { p: ProjectDetail; open: boolean; onClose: () => void; current: number }) {
  const qc = useQueryClient();
  const versions = useQuery({ queryKey: ["script", p.id, "versions"], queryFn: () => api.script.versions(p.id), enabled: open });
  const restore = useMutation({
    mutationFn: (v: number) => api.script.restore(p.id, v),
    onSuccess: (d) => {
      qc.setQueryData(["script", p.id], d);
      void qc.invalidateQueries({ queryKey: ["script", p.id] });
      toast.success(`Restored version ${d.version}`);
      onClose();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Restore failed"),
  });
  return (
    <Modal open={open} onClose={onClose} title="Script versions">
      {versions.data?.length ? (
        <ul className="divide-y divide-line">
          {versions.data.map((v) => (
            <li key={v.id} className="flex items-center justify-between py-2 text-sm">
              <div>
                <p className="font-medium">Version {v.version} {v.version === current && <Badge className="ml-1">current</Badge>}</p>
                <p className="text-xs text-muted">{v.word_count} words · {formatDuration(v.estimated_duration_seconds)} · {new Date(v.created_at).toLocaleString()}</p>
              </div>
              {v.version !== current && <Button size="sm" loading={restore.isPending} onClick={() => restore.mutate(v.version)}>Restore</Button>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">{versions.isLoading ? "Loading…" : "No other versions."}</p>
      )}
    </Modal>
  );
}
