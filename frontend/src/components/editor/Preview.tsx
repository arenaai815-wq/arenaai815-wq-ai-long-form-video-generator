"use client";
import { useEffect, useMemo, useRef } from "react";
import { Play, Pause, SkipBack, SkipForward, Volume2, VolumeX } from "lucide-react";
import { useEditor, clipAt } from "@/store/editor";
import type { CaptionCue, Clip, TimelineDocument } from "@/types/api";
import { cn, formatDuration } from "@/lib/utils";
import { Button } from "@/components/ui";

/**
 * Browser preview of the timeline: shows the visual under the playhead with a CSS approximation of the
 * motion effect, overlays on-screen text + captions, and plays voiceover/music audio in sync.
 * (The authoritative output is the FFmpeg render; this is a lightweight WYSIWYG approximation.)
 */
export function Preview({ cues, muted, onToggleMute }: { cues: CaptionCue[]; muted: boolean; onToggleMute: () => void }) {
  const doc = useEditor((s) => s.doc);
  const playhead = useEditor((s) => s.playhead);
  const playing = useEditor((s) => s.playing);
  const setPlayhead = useEditor((s) => s.setPlayhead);
  const setPlaying = useEditor((s) => s.setPlaying);
  const raf = useRef<number | null>(null);
  const lastTs = useRef<number | null>(null);

  // playback clock
  useEffect(() => {
    if (!playing) {
      lastTs.current = null;
      if (raf.current) cancelAnimationFrame(raf.current);
      return;
    }
    const tick = (ts: number) => {
      const st = useEditor.getState();
      if (lastTs.current != null) {
        const next = st.playhead + (ts - lastTs.current) / 1000;
        if (next >= (st.doc?.duration ?? 0)) {
          st.setPlayhead(st.doc?.duration ?? 0);
          st.setPlaying(false);
          return;
        }
        st.setPlayhead(next);
      }
      lastTs.current = ts;
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [playing]);

  const visual = doc ? clipAt(doc, "video", playhead) : null;
  const text = doc ? clipAt(doc, "text", playhead) : null;
  const cue = useMemo(() => (doc?.captions?.enabled ? cues.find((c) => playhead >= c.start + (doc.captions.timing_offset || 0) && playhead <= c.end + (doc.captions.timing_offset || 0)) : undefined), [cues, playhead, doc]);
  const aspect = doc ? doc.width / doc.height : 16 / 9;

  return (
    <div className="flex h-full flex-col">
      <div className="relative flex min-h-0 flex-1 items-center justify-center bg-black/60 p-3">
        <div className="relative max-h-full overflow-hidden rounded-md bg-black shadow-2xl" style={{ aspectRatio: `${aspect}`, width: "100%", maxWidth: `calc((100vh - 420px) * ${aspect})`, containerType: "inline-size" }}>
          {visual ? <VisualLayer key={visual.clip.id} clip={visual.clip} time={playhead - visual.clip.start} playing={playing} /> : <div className="absolute inset-0 grid place-items-center text-xs text-muted">{doc?.tracks.length ? "Gap — nothing on the video track here" : "Empty timeline"}</div>}
          {text?.clip.text?.content && <TextLayer clip={text.clip} />}
          {cue && doc && <CaptionLayer text={cue.text} style={doc.captions} width={doc.width} />}
          {doc?.watermark?.enabled && doc.watermark.text && (
            <span className={cn("absolute rounded-full bg-black/50 px-2 py-0.5 text-[10px] text-white", doc.watermark.position.includes("top") ? "top-2" : "bottom-2", doc.watermark.position.includes("left") ? "left-2" : "right-2")} style={{ opacity: doc.watermark.opacity }}>{doc.watermark.text}</span>
          )}
        </div>
        <AudioLayer muted={muted} />
      </div>
      <div className="flex items-center gap-2 border-t border-line bg-panel px-3 py-2">
        <Button variant="ghost" size="icon" onClick={() => setPlayhead(0)} title="Start (Home)"><SkipBack className="h-4 w-4" /></Button>
        <Button variant="primary" size="icon" onClick={() => setPlaying(!playing)} title="Play/Pause (Space)">{playing ? <Pause className="h-4 w-4" /> : <Play className="ml-0.5 h-4 w-4" />}</Button>
        <Button variant="ghost" size="icon" onClick={() => setPlayhead(doc?.duration ?? 0)} title="End (End)"><SkipForward className="h-4 w-4" /></Button>
        <span className="ml-2 font-mono text-xs tabular-nums">{formatDuration(playhead, true)} <span className="text-muted">/ {formatDuration(doc?.duration ?? 0)}</span></span>
        <input type="range" min={0} max={doc?.duration ?? 0} step={0.01} value={playhead} onChange={(e) => setPlayhead(parseFloat(e.target.value))} className="mx-3 h-1 flex-1 cursor-pointer appearance-none rounded-full bg-line accent-brand-500" />
        <Button variant="ghost" size="icon" onClick={onToggleMute} title="Mute preview audio">{muted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}</Button>
        <span className="text-[10px] text-muted">{doc ? `${doc.width}×${doc.height} · ${doc.fps}fps` : ""}</span>
      </div>
    </div>
  );
}

function VisualLayer({ clip, time, playing }: { clip: Clip; time: number; playing: boolean }) {
  const p = Math.min(1, Math.max(0, time / Math.max(0.01, clip.duration)));
  const eff = clip.effect?.type ?? "none";
  const k = (clip.effect?.intensity ?? 0.1) * 1.2;
  let transform = "scale(1)";
  switch (eff) {
    case "zoom_in":
      transform = `scale(${1 + k * p})`;
      break;
    case "zoom_out":
      transform = `scale(${1 + k * (1 - p)})`;
      break;
    case "pan_left":
      transform = `scale(${1 + k}) translateX(${k * 50 * (0.5 - p)}%)`;
      break;
    case "pan_right":
      transform = `scale(${1 + k}) translateX(${k * 50 * (p - 0.5)}%)`;
      break;
    case "pan_up":
      transform = `scale(${1 + k}) translateY(${k * 50 * (0.5 - p)}%)`;
      break;
    case "pan_down":
      transform = `scale(${1 + k}) translateY(${k * 50 * (p - 0.5)}%)`;
      break;
    case "ken_burns":
      transform = `scale(${1 + k * p}) translate(${k * 20 * (p - 0.5)}%, ${k * 10 * (0.5 - p)}%)`;
      break;
  }
  const videoRef = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const target = clip.trim_start + time;
    if (Math.abs(v.currentTime - target) > 0.3) v.currentTime = target;
    if (playing && v.paused) void v.play().catch(() => undefined);
    if (!playing && !v.paused) v.pause();
  }, [time, playing, clip.trim_start]);
  const fadeIn = clip.transition_in && clip.transition_in.type !== "none" && time < clip.transition_in.duration ? time / clip.transition_in.duration : 1;
  if (!clip.src_url) {
    return (
      <div className="absolute inset-0 grid place-items-center bg-[radial-gradient(ellipse_at_center,rgba(58,95,255,0.25),rgba(9,11,17,1))] p-8 text-center" style={{ opacity: fadeIn }}>
        <p className="text-lg font-semibold text-white/90">{clip.label || clip.text?.content || "Text card"}</p>
      </div>
    );
  }
  if (clip.asset_kind === "video") {
    return <video ref={videoRef} src={clip.src_url} muted playsInline className="absolute inset-0 h-full w-full object-cover" style={{ opacity: fadeIn }} />;
  }
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={clip.src_url} alt="" className="absolute inset-0 h-full w-full object-cover will-change-transform" style={{ transform, transformOrigin: "center", opacity: fadeIn }} draggable={false} />;
}

function TextLayer({ clip }: { clip: Clip }) {
  const t = clip.text!;
  const pos = t.position || "center";
  const cls = cn(
    "absolute max-w-[80%] px-3 py-1.5 font-semibold leading-tight drop-shadow-lg",
    pos === "center" && "left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-center",
    pos === "top" && "left-1/2 top-[8%] -translate-x-1/2 text-center",
    pos === "bottom" && "left-1/2 bottom-[14%] -translate-x-1/2 text-center",
    pos === "top_left" && "left-[5%] top-[8%]",
    pos === "top_right" && "right-[5%] top-[8%] text-right",
    pos === "bottom_left" && "left-[5%] bottom-[14%]",
    pos === "bottom_right" && "right-[5%] bottom-[14%] text-right",
  );
  return (
    <div className={cls} style={{ color: t.color || "#fff", background: t.background ? `${t.background}b3` : undefined, fontSize: `${Math.max(10, (t.font_size || 56) / 30)}cqw`, borderRadius: 6 }}>
      {t.content}
    </div>
  );
}

function CaptionLayer({ text, style, width }: { text: string; style: TimelineDocument["captions"]; width: number }) {
  const scale = 100 / width; // px in the render → % of the preview width
  const fs = (style.font_size || 44) * scale;
  const outline = (style.outline_width ?? 2) * scale;
  return (
    <div className={cn("pointer-events-none absolute left-0 right-0 flex justify-center px-[6%]", style.position === "top" ? "top-[6%]" : style.position === "center" ? "top-1/2 -translate-y-1/2" : "bottom-0")} style={style.position === "bottom" ? { paddingBottom: `${(style.margin_v || 60) * scale}cqw` } : undefined}>
      <span
        className="whitespace-pre-line text-center font-semibold leading-snug"
        style={{
          color: style.color || "#fff",
          fontSize: `${fs}cqw`,
          background: style.background_color ? `${style.background_color}cc` : undefined,
          padding: style.background_color ? "0.2em 0.5em" : undefined,
          borderRadius: 6,
          WebkitTextStroke: !style.background_color ? `${outline / 3}cqw ${style.outline_color || "#000"}` : undefined,
          paintOrder: "stroke fill",
          textShadow: `0 0 ${outline * 2}cqw rgba(0,0,0,.8)`,
        }}
      >
        {text}
      </span>
    </div>
  );
}

/** Plays voiceover + music clips under the playhead (best-effort sync). */
function AudioLayer({ muted }: { muted: boolean }) {
  const doc = useEditor((s) => s.doc);
  const playhead = useEditor((s) => s.playhead);
  const playing = useEditor((s) => s.playing);
  const els = useRef<Map<string, HTMLAudioElement>>(new Map());
  useEffect(() => {
    if (!doc) return;
    const active = new Set<string>();
    for (const track of doc.tracks) {
      if (!["voiceover", "music", "sfx", "audio"].includes(track.kind) || track.muted) continue;
      for (const clip of track.clips) {
        if (!clip.src_url) continue;
        const inside = playhead >= clip.start && playhead < clip.start + clip.duration;
        if (!inside) continue;
        active.add(clip.id);
        let el = els.current.get(clip.id);
        if (!el) {
          el = new Audio(clip.src_url);
          el.preload = "auto";
          els.current.set(clip.id, el);
        }
        const local = playhead - clip.start;
        let vol = (clip.volume ?? 1) * (track.volume ?? 1);
        if (clip.fade_in && local < clip.fade_in) vol *= local / clip.fade_in;
        if (clip.fade_out && clip.duration - local < clip.fade_out) vol *= Math.max(0, (clip.duration - local) / clip.fade_out);
        el.volume = muted ? 0 : Math.min(1, vol);
        const target = clip.trim_start + local;
        if (Math.abs(el.currentTime - target) > 0.35) el.currentTime = target;
        if (playing && el.paused) void el.play().catch(() => undefined);
        if (!playing && !el.paused) el.pause();
      }
    }
    els.current.forEach((el, id) => {
      if (!active.has(id) && !el.paused) el.pause();
    });
  }, [doc, playhead, playing, muted]);
  useEffect(() => {
    const map = els.current;
    return () => {
      map.forEach((el) => el.pause());
      map.clear();
    };
  }, []);
  return null;
}
