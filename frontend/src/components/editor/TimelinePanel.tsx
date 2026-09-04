"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Volume2, VolumeX, Lock, Unlock, ZoomIn, ZoomOut, Magnet, Scissors, Trash2, Copy, Undo2, Redo2, Music4, Mic2, Type, Film, Captions as CaptionsIcon, Plus } from "lucide-react";
import { useEditor } from "@/store/editor";
import type { CaptionCue, Clip, Track, TrackKind } from "@/types/api";
import { cn, clamp, formatDuration } from "@/lib/utils";
import { Button, Kbd } from "@/components/ui";

const HEADER_W = 176;
const TRACK_H: Record<string, number> = { video: 64, image: 64, text: 34, voiceover: 44, music: 40, sfx: 34, audio: 40, captions: 30 };
const TRACK_ICON: Record<string, React.ComponentType<{ className?: string }>> = { video: Film, image: Film, text: Type, voiceover: Mic2, music: Music4, sfx: Music4, audio: Music4, captions: CaptionsIcon };
const CLIP_COLOR: Record<string, string> = {
  video: "bg-sky-500/25 border-sky-400/60",
  image: "bg-sky-500/25 border-sky-400/60",
  text: "bg-amber-500/25 border-amber-400/60",
  voiceover: "bg-emerald-500/25 border-emerald-400/60",
  music: "bg-violet-500/25 border-violet-400/60",
  sfx: "bg-fuchsia-500/25 border-fuchsia-400/60",
  audio: "bg-violet-500/25 border-violet-400/60",
  captions: "bg-zinc-500/25 border-zinc-400/60",
};

export function TimelinePanel({ cues }: { cues: CaptionCue[] }) {
  const { doc, zoom, setZoom, playhead, setPlayhead, selectedClipId, select, snap, toggleSnap, undo, redo, past, future, splitClipAt, deleteClip, duplicateClip, selectedTrackId, addTrack } = useEditor();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrubbing, setScrubbing] = useState(false);
  const duration = Math.max(doc?.duration ?? 0, 10);
  const width = duration * zoom + 400;

  const timeAt = useCallback(
    (clientX: number) => {
      const el = scrollRef.current;
      if (!el) return 0;
      const rect = el.getBoundingClientRect();
      return clamp((clientX - rect.left - HEADER_W + el.scrollLeft) / zoom, 0, doc?.duration ?? 0);
    },
    [zoom, doc?.duration],
  );

  // keep playhead visible while playing
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const x = playhead * zoom;
    const view = el.clientWidth - HEADER_W;
    if (x < el.scrollLeft || x > el.scrollLeft + view - 40) el.scrollLeft = Math.max(0, x - view / 3);
  }, [playhead, zoom]);

  // wheel zoom (ctrl/cmd + wheel)
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      setZoom(zoom * (e.deltaY < 0 ? 1.15 : 0.87));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoom, setZoom]);

  const onRulerDown = (e: React.MouseEvent) => {
    setScrubbing(true);
    setPlayhead(timeAt(e.clientX));
  };
  useEffect(() => {
    if (!scrubbing) return;
    const move = (e: MouseEvent) => setPlayhead(timeAt(e.clientX));
    const up = () => setScrubbing(false);
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, [scrubbing, setPlayhead, timeAt]);

  const ticks = useMemo(() => {
    const step = zoom > 80 ? 1 : zoom > 40 ? 2 : zoom > 16 ? 5 : zoom > 8 ? 10 : 30;
    const out: number[] = [];
    for (let t = 0; t <= duration + step; t += step) out.push(t);
    return { step, out };
  }, [zoom, duration]);

  const selected = useMemo(() => {
    if (!doc || !selectedClipId) return null;
    for (const t of doc.tracks) {
      const c = t.clips.find((x) => x.id === selectedClipId);
      if (c) return { track: t, clip: c };
    }
    return null;
  }, [doc, selectedClipId]);

  if (!doc) return null;
  const tracks = doc.tracks;

  return (
    <div className="flex h-full flex-col bg-panel">
      <div className="flex items-center gap-1 border-b border-line px-2 py-1.5">
        <Button variant="ghost" size="icon" title="Undo (⌘Z)" disabled={!past.length} onClick={undo}><Undo2 className="h-4 w-4" /></Button>
        <Button variant="ghost" size="icon" title="Redo (⇧⌘Z)" disabled={!future.length} onClick={redo}><Redo2 className="h-4 w-4" /></Button>
        <span className="mx-1 h-5 w-px bg-line" />
        <Button variant="ghost" size="icon" title="Split at playhead (S)" disabled={!selected} onClick={() => selected && splitClipAt(selected.track.id, selected.clip.id, playhead)}><Scissors className="h-4 w-4" /></Button>
        <Button variant="ghost" size="icon" title="Duplicate (⌘D)" disabled={!selected} onClick={() => selected && duplicateClip(selected.track.id, selected.clip.id)}><Copy className="h-4 w-4" /></Button>
        <Button variant="ghost" size="icon" title="Delete (⌫)" disabled={!selected} onClick={() => selected && deleteClip(selected.track.id, selected.clip.id)}><Trash2 className="h-4 w-4" /></Button>
        <span className="mx-1 h-5 w-px bg-line" />
        <Button variant="ghost" size="icon" title="Snap to clips" className={cn(snap && "text-brand-300")} onClick={toggleSnap}><Magnet className="h-4 w-4" /></Button>
        <span className="mx-1 h-5 w-px bg-line" />
        <AddTrackMenu onAdd={(k) => addTrack(k)} />
        <div className="ml-auto flex items-center gap-1">
          <span className="mr-2 hidden text-[10px] text-muted lg:inline"><Kbd>Space</Kbd> play · <Kbd>S</Kbd> split · <Kbd>⌘Z</Kbd> undo · <Kbd>⌘+wheel</Kbd> zoom</span>
          <Button variant="ghost" size="icon" onClick={() => setZoom(zoom / 1.3)}><ZoomOut className="h-4 w-4" /></Button>
          <input type="range" min={4} max={200} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} className="h-1 w-24 cursor-pointer appearance-none rounded-full bg-line accent-brand-500" />
          <Button variant="ghost" size="icon" onClick={() => setZoom(zoom * 1.3)}><ZoomIn className="h-4 w-4" /></Button>
        </div>
      </div>

      <div ref={scrollRef} className="relative min-h-0 flex-1 overflow-auto">
        <div style={{ width: width + HEADER_W }} className="relative">
          {/* ruler */}
          <div className="sticky top-0 z-20 flex h-7 border-b border-line bg-panel">
            <div className="sticky left-0 z-30 w-[176px] shrink-0 border-r border-line bg-panel" />
            <div className="relative flex-1 cursor-ew-resize select-none" onMouseDown={onRulerDown}>
              {ticks.out.map((t) => (
                <div key={t} className="absolute top-0 h-full border-l border-line/70 pl-1 font-mono text-[10px] text-muted" style={{ left: t * zoom }}>
                  {formatDuration(t)}
                </div>
              ))}
            </div>
          </div>

          {/* tracks */}
          {tracks.map((track) => (
            <TrackRow key={track.id} track={track} zoom={zoom} timeAt={timeAt} selected={selectedClipId} selectedTrack={selectedTrackId} onSelect={(c) => select(c, track.id)} cues={track.kind === "captions" ? cues : undefined} snapTargets={snap ? snapTargets(tracks, playhead) : []} />
          ))}
          {/* playhead */}
          <div className="pointer-events-none absolute bottom-0 top-0 z-30 w-px bg-red-400" style={{ left: HEADER_W + playhead * zoom }}>
            <div className="-ml-[5px] h-0 w-0 border-l-[5px] border-r-[5px] border-t-[7px] border-l-transparent border-r-transparent border-t-red-400" />
          </div>
        </div>
      </div>
    </div>
  );
}

function snapTargets(tracks: Track[], playhead: number): number[] {
  const t = new Set<number>([0, playhead]);
  for (const tr of tracks) for (const c of tr.clips) {
    t.add(c.start);
    t.add(c.start + c.duration);
  }
  return Array.from(t);
}

function TrackRow({ track, zoom, timeAt, selected, selectedTrack, onSelect, cues, snapTargets }: { track: Track; zoom: number; timeAt: (x: number) => number; selected: string | null; selectedTrack: string | null; onSelect: (id: string | null) => void; cues?: CaptionCue[]; snapTargets: number[] }) {
  const { updateTrack, moveClip, trimClip, reorderVideoClips, select } = useEditor();
  const h = TRACK_H[track.kind] ?? 40;
  const Icon = TRACK_ICON[track.kind] ?? Film;
  const [drag, setDrag] = useState<{ id: string; mode: "move" | "trim-start" | "trim-end"; originX: number; origStart: number; origDur: number; delta: number } | null>(null);

  useEffect(() => {
    if (!drag) return;
    const move = (e: MouseEvent) => setDrag((d) => (d ? { ...d, delta: (e.clientX - d.originX) / zoom } : d));
    const up = (e: MouseEvent) => {
      setDrag((d) => {
        if (!d) return null;
        const delta = (e.clientX - d.originX) / zoom;
        if (Math.abs(delta) > 0.02) {
          if (d.mode === "move") {
            if (track.kind === "video") {
              // dragging a video clip reorders it (sequence track)
              const clips = [...track.clips].sort((a, b) => a.start - b.start);
              const from = clips.findIndex((c) => c.id === d.id);
              const center = d.origStart + delta + d.origDur / 2;
              let to = clips.findIndex((c) => center < c.start + c.duration / 2);
              if (to < 0) to = clips.length - 1;
              if (to > from) to -= 0;
              if (from !== to) reorderVideoClips(from, to);
            } else {
              let start = Math.max(0, d.origStart + delta);
              const near = snapTargets.find((t) => Math.abs(t - start) * zoom < 8 || Math.abs(t - (start + d.origDur)) * zoom < 8);
              if (near != null) start = Math.abs(near - start) < Math.abs(near - (start + d.origDur)) ? near : near - d.origDur;
              moveClip(track.id, d.id, Math.max(0, start));
            }
          } else {
            trimClip(track.id, d.id, d.mode === "trim-start" ? "start" : "end", delta);
          }
        }
        return null;
      });
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, [drag, zoom, track, moveClip, trimClip, reorderVideoClips, snapTargets]);

  const startDrag = (e: React.MouseEvent, clip: Clip, mode: "move" | "trim-start" | "trim-end") => {
    if (track.locked) return;
    e.stopPropagation();
    e.preventDefault();
    onSelect(clip.id);
    setDrag({ id: clip.id, mode, originX: e.clientX, origStart: clip.start, origDur: clip.duration, delta: 0 });
  };

  return (
    <div className={cn("flex border-b border-line/70", selectedTrack === track.id && "bg-brand-500/5")} style={{ height: h }}>
      <div className="sticky left-0 z-10 flex w-[176px] shrink-0 items-center gap-1.5 border-r border-line bg-panel px-2 text-xs">
        <Icon className="h-3.5 w-3.5 shrink-0 text-muted" />
        <span className="truncate" title={track.name}>{track.name || track.kind}</span>
        <span className="ml-auto flex shrink-0 items-center">
          {track.kind !== "text" && track.kind !== "captions" && (
            <button className="btn-ghost h-6 w-6 p-0" title={track.muted ? "Unmute" : "Mute"} onClick={() => updateTrack(track.id, { muted: !track.muted })}>{track.muted ? <VolumeX className="h-3 w-3 text-red-300" /> : <Volume2 className="h-3 w-3" />}</button>
          )}
          <button className="btn-ghost h-6 w-6 p-0" title={track.locked ? "Unlock" : "Lock"} onClick={() => updateTrack(track.id, { locked: !track.locked })}>{track.locked ? <Lock className="h-3 w-3 text-amber-300" /> : <Unlock className="h-3 w-3" />}</button>
        </span>
      </div>
      <div className="timeline-grid relative flex-1" style={{ backgroundSize: `${zoom * (zoom > 40 ? 1 : 5)}px 100%` }} onMouseDown={(e) => { select(null, track.id); useEditor.getState().setPlayhead(timeAt(e.clientX)); }}>
        {track.kind === "captions" && cues?.map((c) => (
          <div key={c.index} className={cn("absolute top-1 bottom-1 truncate rounded border px-1 text-[9px] leading-[20px] text-fg/80", CLIP_COLOR.captions)} style={{ left: c.start * zoom, width: Math.max(2, (c.end - c.start) * zoom) }} title={c.text}>{c.text}</div>
        ))}
        {track.clips.map((clip) => {
          const dragging = drag?.id === clip.id ? drag : null;
          let left = clip.start;
          let dur = clip.duration;
          if (dragging) {
            if (dragging.mode === "move") left = Math.max(0, dragging.origStart + dragging.delta);
            else if (dragging.mode === "trim-end") dur = Math.max(0.5, dragging.origDur + dragging.delta);
            else {
              const nd = Math.max(0.5, dragging.origDur - dragging.delta);
              left = dragging.origStart + (dragging.origDur - nd);
              dur = nd;
            }
          }
          const isSel = selected === clip.id;
          return (
            <div
              key={clip.id}
              className={cn("group absolute top-1 bottom-1 select-none overflow-hidden rounded-md border text-[10px] shadow-sm transition-shadow", CLIP_COLOR[track.kind] ?? CLIP_COLOR.audio, isSel && "ring-2 ring-white/80", track.locked ? "cursor-not-allowed opacity-70" : "cursor-grab active:cursor-grabbing", dragging && "z-20 opacity-90")}
              style={{ left: left * zoom, width: Math.max(4, dur * zoom) }}
              onMouseDown={(e) => startDrag(e, clip, "move")}
              onDoubleClick={() => useEditor.getState().setPlayhead(clip.start)}
              title={`${clip.label || clip.text?.content || clip.asset_kind || ""} · ${formatDuration(clip.start)} → ${formatDuration(clip.start + clip.duration)}`}
            >
              {(track.kind === "video" || track.kind === "image") && clip.src_url && clip.asset_kind !== "video" && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={clip.src_url} alt="" className="pointer-events-none absolute inset-0 h-full w-full object-cover opacity-50" draggable={false} />
              )}
              {(track.kind === "voiceover" || track.kind === "music" || track.kind === "audio" || track.kind === "sfx") && <Waveform seed={clip.id} volume={clip.volume} fadeIn={clip.fade_in} fadeOut={clip.fade_out} duration={clip.duration} />}
              <div className="relative flex h-full flex-col justify-between px-1.5 py-0.5">
                <span className="truncate font-medium text-white drop-shadow">{clip.label || clip.text?.content || (clip.asset_kind ? clip.asset_kind : "clip")}</span>
                {track.kind === "video" && (
                  <span className="flex items-center gap-1 text-[9px] text-white/80">
                    {clip.transition_in && clip.transition_in.type !== "none" && <span className="rounded bg-black/40 px-1">⇄ {clip.transition_in.type}</span>}
                    {clip.effect && clip.effect.type !== "none" && <span className="rounded bg-black/40 px-1">{clip.effect.type.replace("_", " ")}</span>}
                    <span className="ml-auto font-mono">{formatDuration(dur)}</span>
                  </span>
                )}
              </div>
              {!track.locked && (
                <>
                  <div className="absolute inset-y-0 left-0 w-1.5 cursor-w-resize bg-white/0 group-hover:bg-white/40" onMouseDown={(e) => startDrag(e, clip, "trim-start")} />
                  <div className="absolute inset-y-0 right-0 w-1.5 cursor-e-resize bg-white/0 group-hover:bg-white/40" onMouseDown={(e) => startDrag(e, clip, "trim-end")} />
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Deterministic pseudo-waveform (real peaks would need decoding; this keeps the timeline light). */
function Waveform({ seed, volume, fadeIn, fadeOut, duration }: { seed: string; volume: number; fadeIn: number; fadeOut: number; duration: number }) {
  const bars = useMemo(() => {
    let h = 0;
    for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    const out: number[] = [];
    for (let i = 0; i < 120; i++) {
      h = (h * 1103515245 + 12345) >>> 0;
      out.push(0.25 + ((h >>> 16) % 1000) / 1400);
    }
    return out;
  }, [seed]);
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full" preserveAspectRatio="none" viewBox="0 0 120 40">
      {bars.map((b, i) => {
        const t = (i / 120) * duration;
        let g = Math.min(1, volume);
        if (fadeIn && t < fadeIn) g *= t / fadeIn;
        if (fadeOut && duration - t < fadeOut) g *= Math.max(0, (duration - t) / fadeOut);
        const hh = b * 36 * g;
        return <rect key={i} x={i} y={20 - hh / 2} width={0.7} height={hh} fill="currentColor" className="text-white/40" />;
      })}
    </svg>
  );
}

function AddTrackMenu({ onAdd }: { onAdd: (k: TrackKind) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <Button variant="ghost" size="sm" onClick={() => setOpen((o) => !o)}><Plus className="h-3.5 w-3.5" /> Track</Button>
      {open && (
        <div className="absolute left-0 top-8 z-40 w-40 rounded-lg border border-line bg-panel2 p-1 text-xs shadow-xl" onMouseLeave={() => setOpen(false)}>
          {(["music", "sfx", "audio", "text"] as TrackKind[]).map((k) => (
            <button key={k} className="flex w-full items-center gap-2 rounded px-2 py-1.5 hover:bg-panel" onClick={() => { onAdd(k); setOpen(false); }}>
              {k === "text" ? <Type className="h-3.5 w-3.5" /> : <Music4 className="h-3.5 w-3.5" />} {k[0].toUpperCase() + k.slice(1)} track
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
