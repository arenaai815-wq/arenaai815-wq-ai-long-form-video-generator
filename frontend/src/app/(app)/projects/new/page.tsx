"use client";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Sparkles, Save, Wand2, Coins } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { ProjectCreate } from "@/types/api";
import { Alert, Button, Card, CardHeader, Field, Input, PageHeader, Select, Slider, Textarea, Toggle } from "@/components/ui";
import { cn } from "@/lib/utils";

const DURATIONS = [1, 2, 5, 10, 20, 30, 45, 60, 90];
const TONES = ["documentary", "engaging", "educational", "conversational", "dramatic", "inspirational", "humorous", "authoritative", "calm"];
const FORMATS = ["documentary", "explainer", "listicle", "story", "essay", "tutorial", "news analysis", "history", "biography"];
const STYLES = ["cinematic", "photorealistic", "illustration", "3d render", "watercolor", "minimalist", "retro", "dark moody", "bright & clean"];
const LANGS: [string, string][] = [["en", "English"], ["es", "Spanish"], ["fr", "French"], ["de", "German"], ["pt", "Portuguese"], ["it", "Italian"], ["hi", "Hindi"], ["ar", "Arabic"], ["ja", "Japanese"], ["zh", "Chinese"], ["yo", "Yoruba"], ["sw", "Swahili"]];
const ASPECTS = [["16:9", "Landscape · YouTube"], ["9:16", "Vertical · Shorts"], ["1:1", "Square"], ["4:5", "Portrait"]];
const RES = ["720p", "1080p", "1440p", "4k"];

export default function NewProjectPage() {
  const router = useRouter();
  const [form, setForm] = useState<ProjectCreate>({
    title: "",
    topic: "",
    description: "",
    niche: "",
    target_audience: "",
    language: "en",
    tone: "documentary",
    video_format: "documentary",
    target_duration_minutes: 10,
    aspect_ratio: "16:9",
    resolution: "1080p",
    visual_style: "cinematic",
  });
  const [visualsMode, setVisualsMode] = useState<"ai_image" | "ai_video" | "stock" | "mixed">("ai_image");
  const [captions, setCaptions] = useState(true);
  const [music, setMusic] = useState(true);
  const [intro, setIntro] = useState(true);
  const [autoStart, setAutoStart] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const voices = useQuery({ queryKey: ["voices", form.language], queryFn: () => api.voiceovers.voices({ language: form.language }) });
  const [voiceId, setVoiceId] = useState<string>("");

  const set = <K extends keyof ProjectCreate>(k: K, v: ProjectCreate[K]) => setForm((f) => ({ ...f, [k]: v }));

  const estimate = useMemo(() => {
    // Mirrors backend billing_service.estimate_project_cost (research 5, script 2/min, tts 3/1k chars @150wpm, images 4 each @9s, render 6/min).
    const mins = form.target_duration_minutes;
    const words = mins * 150;
    const research = 5;
    const script = 2 * mins;
    const tts = Math.ceil((words * 6) / 1000) * 3;
    const scenes = Math.ceil((mins * 60) / 9);
    const images = visualsMode === "ai_video" ? scenes * 25 : visualsMode === "stock" ? 0 : scenes * 4;
    const render = 6 * mins;
    return { total: research + script + tts + images + render, research, script, tts, images, render, scenes };
  }, [form.target_duration_minutes, visualsMode]);

  const create = useMutation({
    mutationFn: async (start: boolean) => {
      const voice = voices.data?.find((v) => v.id === voiceId);
      const payload: ProjectCreate = {
        ...form,
        niche: form.niche || null,
        target_audience: form.target_audience || null,
        description: form.description || null,
        settings: {
          visuals: { mode: visualsMode, ai_video_ratio: visualsMode === "mixed" ? 0.3 : 0, motion: "ken_burns", transition: "fade", transition_duration: 0.6, image_provider: null, video_provider: null },
          captions: { enabled: captions, burn_in: captions } as never,
          music: { enabled: music } as never,
          intro: { enabled: intro, duration: 3, title: null, subtitle: null },
          outro: { enabled: intro, duration: 4, text: "Thanks for watching", cta: "Subscribe for more" },
          ...(voice ? { voice: { provider: voice.provider, voice_id: voice.id, voice_name: voice.name, language: form.language, style: voice.styles[0] || "narration", speed: 1 } } : {}),
        } as never,
      };
      const project = await api.projects.create(payload);
      if (start) {
        await api.projects.generate(project.id, { idempotency_key: `create-${project.id}` });
      }
      return { project, start };
    },
    onSuccess: ({ project, start }) => {
      toast.success(start ? "Project created — pipeline started" : "Draft saved");
      router.push(start ? `/projects/${project.id}` : `/projects/${project.id}`);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not create project"),
  });

  const valid = form.title.trim().length > 0 && form.topic.trim().length >= 3;

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="New project" description="Describe the video you want. Everything here can be changed later." />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {error && <Alert tone="error">{error}</Alert>}
          <Card>
            <CardHeader title="Concept" description="What the video is about and who it is for." />
            <div className="grid gap-4">
              <Field label="Title"><Input value={form.title} onChange={(e) => set("title", e.target.value)} placeholder="The Silent History of the Sahara" /></Field>
              <Field label="Topic / brief" hint="Be specific: angle, key questions, what to include or avoid.">
                <Textarea rows={4} value={form.topic} onChange={(e) => set("topic", e.target.value)} placeholder="How the Sahara turned from a green savanna into the largest hot desert on Earth — climate cycles, lost civilisations and what it means for the future." />
              </Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Niche"><Input value={form.niche ?? ""} onChange={(e) => set("niche", e.target.value)} placeholder="history & science" /></Field>
                <Field label="Target audience"><Input value={form.target_audience ?? ""} onChange={(e) => set("target_audience", e.target.value)} placeholder="curious adults, 25–45" /></Field>
              </div>
              <Field label="Notes for the writer (optional)"><Textarea rows={2} value={form.description ?? ""} onChange={(e) => set("description", e.target.value)} placeholder="Open with a mystery. Avoid jargon. Mention the Green Sahara period explicitly." /></Field>
            </div>
          </Card>

          <Card>
            <CardHeader title="Format" description="Length, language and voice." />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Language">
                <Select value={form.language} onChange={(e) => { set("language", e.target.value); setVoiceId(""); }}>{LANGS.map(([c, n]) => <option key={c} value={c}>{n}</option>)}</Select>
              </Field>
              <Field label="Tone"><Select value={form.tone} onChange={(e) => set("tone", e.target.value)}>{TONES.map((t) => <option key={t}>{t}</option>)}</Select></Field>
              <Field label="Video format"><Select value={form.video_format} onChange={(e) => set("video_format", e.target.value)}>{FORMATS.map((t) => <option key={t}>{t}</option>)}</Select></Field>
              <Field label="Narrator voice" hint={voices.data?.length ? `${voices.data.length} voices available` : "Loading voices…"}>
                <Select value={voiceId} onChange={(e) => setVoiceId(e.target.value)}>
                  <option value="">Default for language</option>
                  {voices.data?.map((v) => <option key={v.id} value={v.id}>{v.name} · {v.gender || "–"} · {v.accent || v.language}{v.is_premium ? " · premium" : ""}</option>)}
                </Select>
              </Field>
            </div>
            <div className="mt-5">
              <div className="flex items-center justify-between">
                <label className="label mb-0">Target duration</label>
                <span className="text-sm font-semibold tabular-nums">{form.target_duration_minutes} min</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {DURATIONS.map((d) => (
                  <button key={d} type="button" onClick={() => set("target_duration_minutes", d)} className={cn("rounded-md border px-2.5 py-1 text-xs", form.target_duration_minutes === d ? "border-brand-500 bg-brand-500/15 text-brand-100" : "border-line text-muted hover:text-fg")}>
                    {d}m
                  </button>
                ))}
              </div>
              <Slider className="mt-3" min={1} max={120} step={1} value={form.target_duration_minutes} onChange={(v) => set("target_duration_minutes", Math.round(v))} />
              <p className="mt-1 text-xs text-muted">≈ {(form.target_duration_minutes * 150).toLocaleString()} words · ≈ {estimate.scenes} scenes</p>
            </div>
          </Card>

          <Card>
            <CardHeader title="Look" description="Aspect ratio, resolution and how visuals are produced." />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Aspect ratio">
                <div className="grid grid-cols-2 gap-2">
                  {ASPECTS.map(([a, l]) => (
                    <button key={a} type="button" onClick={() => set("aspect_ratio", a)} className={cn("rounded-lg border px-3 py-2 text-left text-xs", form.aspect_ratio === a ? "border-brand-500 bg-brand-500/15" : "border-line hover:border-brand-500/40")}>
                      <span className="font-semibold">{a}</span>
                      <span className="block text-muted">{l}</span>
                    </button>
                  ))}
                </div>
              </Field>
              <div className="space-y-4">
                <Field label="Resolution"><Select value={form.resolution} onChange={(e) => set("resolution", e.target.value)}>{RES.map((r) => <option key={r}>{r}</option>)}</Select></Field>
                <Field label="Visual style"><Select value={form.visual_style} onChange={(e) => set("visual_style", e.target.value)}>{STYLES.map((s) => <option key={s}>{s}</option>)}</Select></Field>
              </div>
            </div>
            <Field label="Visual source" className="mt-4">
              <div className="grid gap-2 sm:grid-cols-4">
                {([["ai_image", "AI images", "Generated stills with Ken Burns motion"], ["ai_video", "AI video", "Generated clips per scene (higher cost)"], ["stock", "Stock footage", "Search & import from stock providers"], ["mixed", "Mixed", "AI images with some AI video"]] as const).map(([id, l, d]) => (
                  <button key={id} type="button" onClick={() => setVisualsMode(id)} className={cn("rounded-lg border px-3 py-2 text-left text-xs", visualsMode === id ? "border-brand-500 bg-brand-500/15" : "border-line hover:border-brand-500/40")}>
                    <span className="font-semibold">{l}</span>
                    <span className="block text-muted">{d}</span>
                  </button>
                ))}
              </div>
            </Field>
            <div className="mt-4 flex flex-wrap gap-6">
              <Toggle checked={captions} onChange={setCaptions} label="Burn-in captions" />
              <Toggle checked={music} onChange={setMusic} label="Background music" />
              <Toggle checked={intro} onChange={setIntro} label="Intro & outro cards" />
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="sticky top-4">
            <CardHeader title="Estimated cost" description="Charged as stages complete." />
            <div className="flex items-end gap-2">
              <span className="text-3xl font-semibold tabular-nums">{estimate.total}</span>
              <span className="mb-1 text-sm text-muted">credits</span>
            </div>
            <ul className="mt-3 space-y-1 text-xs text-muted">
              <li className="flex justify-between"><span>Research</span><span>{estimate.research}</span></li>
              <li className="flex justify-between"><span>Script</span><span>{estimate.script}</span></li>
              <li className="flex justify-between"><span>Voiceover</span><span>{estimate.tts}</span></li>
              <li className="flex justify-between"><span>Visuals ({estimate.scenes} scenes)</span><span>{estimate.images}</span></li>
              <li className="flex justify-between"><span>Render</span><span>{estimate.render}</span></li>
            </ul>
            <div className="mt-5 space-y-2">
              <Toggle checked={autoStart} onChange={setAutoStart} label="Start the full pipeline now" />
              <p className="text-xs text-muted">{autoStart ? "Research → script → scenes → voiceover → visuals → captions → render. You can review and edit each stage while it runs." : "Save as a draft and run stages one by one from the project page."}</p>
            </div>
            <div className="mt-4 grid gap-2">
              <Button variant="primary" disabled={!valid} loading={create.isPending && autoStart} onClick={() => create.mutate(autoStart)}>
                {autoStart ? <><Wand2 className="h-4 w-4" /> Create & generate</> : <><Save className="h-4 w-4" /> Save draft</>}
              </Button>
              {autoStart && (
                <Button variant="ghost" disabled={!valid} loading={create.isPending && !autoStart} onClick={() => create.mutate(false)}>
                  <Save className="h-4 w-4" /> Just save as draft
                </Button>
              )}
            </div>
            <p className="mt-3 flex items-center gap-1 text-[11px] text-muted"><Coins className="h-3 w-3" /> Credits are only reserved per stage; failed stages are refunded.</p>
          </Card>
          <Card className="bg-gradient-to-br from-brand-600/20 to-panel">
            <div className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="h-4 w-4 text-brand-300" /> Tips for better videos</div>
            <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-muted">
              <li>Longer briefs give the researcher more to work with.</li>
              <li>10–20 minutes is the sweet spot for watch time.</li>
              <li>You can regenerate any script section or scene visual individually.</li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
