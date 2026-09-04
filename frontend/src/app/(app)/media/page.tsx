"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Upload, Trash2, Film, Image as ImageIcon, Music4, Search, Download, Star, StarOff, HardDrive } from "lucide-react";
import { api, ApiError, uploadFile } from "@/lib/api";
import type { MediaAsset, StockSearchResult } from "@/types/api";
import { Button, Card, EmptyState, Input, Modal, PageHeader, ProgressBar, Select, Skeleton, Tabs } from "@/components/ui";
import { cn, formatBytes, formatDuration, formatRelative } from "@/lib/utils";

export default function MediaPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"visual" | "audio" | "stock">("visual");
  const [kind, setKind] = useState("");
  const [source, setSource] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [progress, setProgress] = useState<number | null>(null);
  const [preview, setPreview] = useState<MediaAsset | null>(null);
  const storage = useQuery({ queryKey: ["storage"], queryFn: api.media.storage });
  const media = useQuery({ queryKey: ["media", "library", { kind, source, q, page }], queryFn: () => api.media.list({ kind: kind || undefined, source: source || undefined, q: q || undefined, page, page_size: 40 }), enabled: tab === "visual" });
  const audio = useQuery({ queryKey: ["audio-library", "all"], queryFn: () => api.media.audio(), enabled: tab === "audio" });
  const projects = useQuery({ queryKey: ["projects", "names"], queryFn: () => api.projects.list({ page_size: 100 }) });

  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const f of files) {
        setProgress(0);
        await uploadFile(f, { onProgress: setProgress, audio_kind: f.type.startsWith("audio/") ? "music" : undefined });
      }
    },
    onSuccess: () => {
      toast.success("Upload complete");
      setProgress(null);
      void qc.invalidateQueries({ queryKey: ["media"] });
      void qc.invalidateQueries({ queryKey: ["audio-library"] });
      void qc.invalidateQueries({ queryKey: ["storage"] });
    },
    onError: (e) => {
      setProgress(null);
      toast.error(e instanceof Error ? e.message : "Upload failed");
    },
  });
  const del = useMutation({
    mutationFn: (id: string) => api.media.remove(id),
    onSuccess: () => {
      toast.success("Deleted");
      setPreview(null);
      void qc.invalidateQueries({ queryKey: ["media"] });
      void qc.invalidateQueries({ queryKey: ["storage"] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Delete failed"),
  });
  const delAudio = useMutation({
    mutationFn: (id: string) => api.media.deleteAudio(id),
    onSuccess: () => {
      toast.success("Deleted");
      void qc.invalidateQueries({ queryKey: ["audio-library"] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Delete failed"),
  });
  const toggleReusable = useMutation({
    mutationFn: (a: MediaAsset) => api.media.update(a.id, { is_reusable: !a.is_reusable }),
    onSuccess: (a) => {
      setPreview(a);
      void qc.invalidateQueries({ queryKey: ["media"] });
    },
  });
  const projectName = (id: string | null) => projects.data?.items.find((p) => p.id === id)?.title ?? (id ? id.slice(0, 8) : "Library");
  const pct = storage.data ? Math.min(100, (storage.data.used_bytes / Math.max(1, storage.data.limit_bytes)) * 100) : 0;

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Media library"
        description="Every generated, imported and uploaded asset — stored in object storage and served via signed URLs."
        actions={
          <label className="btn-primary cursor-pointer">
            <Upload className="h-4 w-4" /> Upload
            <input type="file" multiple accept="image/*,video/*,audio/*" className="hidden" onChange={(e) => e.target.files?.length && upload.mutate(Array.from(e.target.files))} />
          </label>
        }
      />
      {progress !== null && (
        <Card className="mb-4 py-3">
          <div className="flex items-center justify-between text-xs"><span>Uploading…</span><span>{progress}%</span></div>
          <ProgressBar value={progress} className="mt-2" />
        </Card>
      )}
      <div className="mb-4 grid gap-4 md:grid-cols-[1fr_auto]">
        <Tabs value={tab} onChange={setTab} tabs={[{ id: "visual", label: "Images & video" }, { id: "audio", label: "Music & SFX" }, { id: "stock", label: "Stock search" }]} className="w-full max-w-md" />
        <Card className="flex items-center gap-3 py-2">
          <HardDrive className="h-4 w-4 text-muted" />
          <div className="w-48">
            <div className="flex justify-between text-[11px] text-muted"><span>{storage.data ? formatBytes(storage.data.used_bytes) : "…"}</span><span>{storage.data ? formatBytes(storage.data.limit_bytes, 0) : ""}</span></div>
            <ProgressBar value={pct} className="mt-1" tone={pct > 90 ? "red" : "brand"} />
          </div>
          <span className="text-xs text-muted">{storage.data?.asset_count ?? 0} assets</span>
        </Card>
      </div>

      {tab === "visual" && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <div className="relative w-64"><Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted" /><Input className="pl-8" placeholder="Search filename, prompt, tags" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} /></div>
            <Select className="w-36" value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }}><option value="">All types</option><option value="image">Images</option><option value="video">Video</option></Select>
            <Select className="w-40" value={source} onChange={(e) => { setSource(e.target.value); setPage(1); }}><option value="">All sources</option><option value="ai_image">AI images</option><option value="ai_video">AI video</option><option value="stock">Stock</option><option value="upload">Uploads</option><option value="render">Renders</option></Select>
          </div>
          {media.isLoading ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">{Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="aspect-video" />)}</div>
          ) : media.data?.items.length ? (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                {media.data.items.map((a) => (
                  <button key={a.id} onClick={() => setPreview(a)} className="card group overflow-hidden text-left transition hover:border-brand-500/60">
                    <div className="relative aspect-video bg-panel2">
                      {a.thumbnail_url || (a.kind === "image" && a.url) ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={a.thumbnail_url || a.url || ""} alt="" className="h-full w-full object-cover" loading="lazy" />
                      ) : (
                        <div className="grid h-full w-full place-items-center text-muted">{a.kind === "video" ? <Film className="h-6 w-6" /> : <ImageIcon className="h-6 w-6" />}</div>
                      )}
                      <span className="absolute left-1.5 top-1.5 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">{a.source.replace("_", " ")}</span>
                      {a.duration_seconds && <span className="absolute bottom-1.5 right-1.5 rounded bg-black/60 px-1 font-mono text-[10px] text-white">{formatDuration(a.duration_seconds)}</span>}
                      {a.is_reusable && <Star className="absolute right-1.5 top-1.5 h-3.5 w-3.5 fill-amber-300 text-amber-300" />}
                    </div>
                    <div className="p-2">
                      <p className="truncate text-xs font-medium">{a.filename}</p>
                      <p className="truncate text-[10px] text-muted">{projectName(a.project_id)} · {formatBytes(a.size_bytes)} · {formatRelative(a.created_at)}</p>
                    </div>
                  </button>
                ))}
              </div>
              {media.data.total > media.data.page_size && (
                <div className="mt-4 flex items-center justify-center gap-2 text-sm">
                  <Button size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
                  <span className="text-muted">Page {page} of {Math.ceil(media.data.total / media.data.page_size)}</span>
                  <Button size="sm" disabled={page * media.data.page_size >= media.data.total} onClick={() => setPage(page + 1)}>Next</Button>
                </div>
              )}
            </>
          ) : (
            <EmptyState icon={<ImageIcon className="h-6 w-6" />} title="No media yet" description="Generated visuals, stock imports and uploads will show up here." />
          )}
        </>
      )}

      {tab === "audio" && (
        <Card>
          {audio.data?.length ? (
            <ul className="divide-y divide-line">
              {audio.data.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                  <Music4 className="h-4 w-4 text-muted" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{a.filename}</p>
                    <p className="text-xs text-muted">{a.kind} · {a.mood || "—"} · {formatDuration(a.duration_seconds)} · {formatBytes(a.size_bytes)} {a.is_system && "· built-in"} {a.license && `· ${a.license}`}</p>
                  </div>
                  {a.url && <audio src={a.url} controls preload="none" className="h-8 w-64" />}
                  {a.url && <a className="btn-ghost h-8 w-8 p-0" href={a.url} download><Download className="h-4 w-4" /></a>}
                  {!a.is_system && <Button variant="ghost" size="icon" onClick={() => confirm("Delete this audio asset?") && delAudio.mutate(a.id)}><Trash2 className="h-4 w-4" /></Button>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">{audio.isLoading ? "Loading…" : "No audio assets."}</p>
          )}
        </Card>
      )}

      {tab === "stock" && <StockSearch />}

      <Modal open={!!preview} onClose={() => setPreview(null)} title={preview?.filename} size="lg" footer={preview && <><Button variant="ghost" onClick={() => toggleReusable.mutate(preview)}>{preview.is_reusable ? <><StarOff className="h-4 w-4" /> Remove from reusable</> : <><Star className="h-4 w-4" /> Mark reusable</>}</Button>{preview.url && <a className="btn-secondary" href={preview.url} download><Download className="h-4 w-4" /> Download</a>}<Button variant="danger" onClick={() => confirm("Delete this asset? Scenes using it will lose their visual.") && del.mutate(preview.id)}><Trash2 className="h-4 w-4" /> Delete</Button></>}>
        {preview && (
          <div className="space-y-3">
            <div className="overflow-hidden rounded-lg bg-black">
              {preview.kind === "video" ? <video src={preview.url ?? undefined} controls className="max-h-[50vh] w-full" /> : // eslint-disable-next-line @next/next/no-img-element
              <img src={preview.url ?? preview.thumbnail_url ?? ""} alt="" className="max-h-[50vh] w-full object-contain" />}
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
              <dt className="text-muted">Type</dt><dd>{preview.kind} · {preview.content_type}</dd>
              <dt className="text-muted">Source</dt><dd>{preview.source}{preview.provider ? ` · ${preview.provider}` : ""}</dd>
              <dt className="text-muted">Size</dt><dd>{preview.width}×{preview.height} · {formatBytes(preview.size_bytes)}</dd>
              <dt className="text-muted">Project</dt><dd className="truncate">{projectName(preview.project_id)}</dd>
            </dl>
            {preview.prompt && <p className="rounded-lg bg-panel2 p-2 text-xs text-muted"><span className="font-semibold text-fg">Prompt:</span> {preview.prompt}</p>}
          </div>
        )}
      </Modal>
    </div>
  );
}

function StockSearch() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [kind, setKind] = useState("video");
  const results = useQuery({ queryKey: ["stock", term, kind], queryFn: () => api.media.stockSearch({ q: term, kind, per_page: 30 }), enabled: term.length > 1 });
  const imp = useMutation({
    mutationFn: (item: StockSearchResult) => api.media.stockImport(item),
    onSuccess: () => {
      toast.success("Imported to library");
      void qc.invalidateQueries({ queryKey: ["media"] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Import failed"),
  });
  return (
    <Card>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); setTerm(q); }}>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search stock footage or photos…" />
        <Select className="w-32" value={kind} onChange={(e) => setKind(e.target.value)}><option value="video">Video</option><option value="image">Photos</option></Select>
        <Button type="submit" variant="primary"><Search className="h-4 w-4" /> Search</Button>
      </form>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {results.isLoading && <p className="col-span-full text-sm text-muted">Searching…</p>}
        {results.data?.map((r) => (
          <div key={r.id} className={cn("card group overflow-hidden")}>
            <div className="relative aspect-video bg-panel2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {r.thumbnail_url ? <img src={r.thumbnail_url} alt="" className="h-full w-full object-cover" /> : <div className="grid h-full w-full place-items-center text-muted"><Film className="h-5 w-5" /></div>}
              <span className="absolute bottom-1 left-1 rounded bg-black/60 px-1 text-[10px] text-white">{r.source}{r.duration_seconds ? ` · ${formatDuration(r.duration_seconds)}` : ""}</span>
            </div>
            <div className="flex items-center justify-between p-2 text-xs">
              <span className="truncate text-muted">{r.author || r.license}</span>
              <Button size="sm" loading={imp.isPending && imp.variables?.id === r.id} onClick={() => imp.mutate(r)}>Import</Button>
            </div>
          </div>
        ))}
        {results.data && !results.data.length && <p className="col-span-full text-sm text-muted">No results. Configure <code>STOCK_PROVIDER=pexels</code> (with <code>PEXELS_API_KEY</code>) for live search.</p>}
      </div>
    </Card>
  );
}
