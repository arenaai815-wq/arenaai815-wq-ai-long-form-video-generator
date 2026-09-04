"use client";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { KeyRound, Shield, User as UserIcon, Plug, Trash2, Plus, Copy, Check } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/store/auth";
import { Alert, Badge, Button, Card, CardHeader, Field, Input, Modal, PageHeader, Select, Tabs } from "@/components/ui";
import { cn, formatDate, formatRelative } from "@/lib/utils";

export default function SettingsPage() {
  const [tab, setTab] = useState<"profile" | "security" | "api" | "providers">("profile");
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Settings" description="Profile, security, API access and AI provider configuration." />
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "profile", label: "Profile" }, { id: "security", label: "Security" }, { id: "api", label: "API keys" }, { id: "providers", label: "AI providers" }]} className="mb-6 max-w-xl" />
      {tab === "profile" && <Profile />}
      {tab === "security" && <Security />}
      {tab === "api" && <ApiKeys />}
      {tab === "providers" && <Providers />}
    </div>
  );
}

function Profile() {
  const { user, setUser } = useAuth();
  const [name, setName] = useState(user?.full_name ?? "");
  const [defaults, setDefaults] = useState({ language: "en", tone: "documentary", resolution: "1080p", aspect_ratio: "16:9", voice_id: "" });
  useEffect(() => {
    const prefs = (user?.preferences?.defaults as typeof defaults | undefined) ?? undefined;
    if (prefs) setDefaults((d) => ({ ...d, ...prefs }));
  }, [user]);
  const voices = useQuery({ queryKey: ["voices", defaults.language], queryFn: () => api.voiceovers.voices({ language: defaults.language }) });
  const save = useMutation({
    mutationFn: () => api.auth.updateMe({ full_name: name, preferences: { ...(user?.preferences ?? {}), defaults } }),
    onSuccess: (u) => {
      setUser(u);
      toast.success("Profile saved");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Save failed"),
  });
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader title="Profile" action={<UserIcon className="h-4 w-4 text-muted" />} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Full name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Email"><Input value={user?.email ?? ""} disabled /></Field>
        </div>
        <CardHeader title="Defaults for new projects" description="Pre-fills the new project form." className="mt-6" />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Language"><Select value={defaults.language} onChange={(e) => setDefaults({ ...defaults, language: e.target.value, voice_id: "" })}>{["en", "es", "fr", "de", "pt", "it", "hi", "ar", "ja", "zh", "yo", "sw"].map((l) => <option key={l}>{l}</option>)}</Select></Field>
          <Field label="Tone"><Input value={defaults.tone} onChange={(e) => setDefaults({ ...defaults, tone: e.target.value })} /></Field>
          <Field label="Resolution"><Select value={defaults.resolution} onChange={(e) => setDefaults({ ...defaults, resolution: e.target.value })}>{["720p", "1080p", "1440p", "4k"].map((l) => <option key={l}>{l}</option>)}</Select></Field>
          <Field label="Aspect ratio"><Select value={defaults.aspect_ratio} onChange={(e) => setDefaults({ ...defaults, aspect_ratio: e.target.value })}>{["16:9", "9:16", "1:1", "4:5"].map((l) => <option key={l}>{l}</option>)}</Select></Field>
          <Field label="Preferred voice" className="sm:col-span-2"><Select value={defaults.voice_id} onChange={(e) => setDefaults({ ...defaults, voice_id: e.target.value })}><option value="">Provider default</option>{voices.data?.map((v) => <option key={v.id} value={v.id}>{v.name} · {v.gender || "–"} · {v.accent || v.language} · {v.provider}</option>)}</Select></Field>
        </div>
        <div className="mt-4 flex justify-end"><Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>Save</Button></div>
      </Card>
      <Card>
        <CardHeader title="Account" />
        <dl className="grid grid-cols-2 gap-y-2 text-xs">
          <dt className="text-muted">Member since</dt><dd>{user ? new Date(user.created_at).toLocaleDateString() : ""}</dd>
          <dt className="text-muted">Last login</dt><dd>{formatRelative(user?.last_login_at)}</dd>
          <dt className="text-muted">Verified</dt><dd>{user?.is_verified ? "yes" : "no"}</dd>
          <dt className="text-muted">Credits</dt><dd>{user?.credits_balance}</dd>
        </dl>
      </Card>
    </div>
  );
}

function Security() {
  const qc = useQueryClient();
  const [pw, setPw] = useState({ current: "", next: "", confirm: "" });
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: api.auth.sessions });
  const change = useMutation({
    mutationFn: () => api.auth.changePassword(pw.current, pw.next),
    onSuccess: () => {
      toast.success("Password changed — other sessions were signed out");
      setPw({ current: "", next: "", confirm: "" });
      void qc.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed"),
  });
  const revoke = useMutation({ mutationFn: (id: string) => api.auth.revokeSession(id), onSuccess: () => { toast.success("Session revoked"); void qc.invalidateQueries({ queryKey: ["sessions"] }); }, onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed") });
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader title="Change password" action={<Shield className="h-4 w-4 text-muted" />} />
        <div className="space-y-3">
          <Field label="Current password"><Input type="password" autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} /></Field>
          <Field label="New password" hint="At least 8 characters"><Input type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></Field>
          <Field label="Confirm new password" error={pw.confirm && pw.confirm !== pw.next ? "Passwords do not match" : undefined}><Input type="password" autoComplete="new-password" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} /></Field>
          <Button variant="primary" disabled={!pw.current || pw.next.length < 8 || pw.next !== pw.confirm} loading={change.isPending} onClick={() => change.mutate()}>Update password</Button>
        </div>
        <Alert tone="info" className="mt-4">Passwords are hashed with Argon2. Access tokens are short-lived JWTs; refresh tokens are revocable sessions.</Alert>
      </Card>
      <Card>
        <CardHeader title="Active sessions" description="Sign out devices you don't recognise." />
        <ul className="divide-y divide-line">
          {sessions.data?.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-3 py-2 text-xs">
              <div className="min-w-0">
                <p className="truncate font-medium">{s.user_agent || "Unknown device"} {s.is_current && <Badge className="ml-1 border-emerald-500/40 text-emerald-300">this device</Badge>}</p>
                <p className="text-muted">{s.ip_address || "—"} · started {formatRelative(s.created_at)} · last used {formatRelative(s.last_used_at)} · expires {formatDate(s.expires_at)}</p>
              </div>
              {!s.is_current && <Button size="sm" variant="ghost" onClick={() => revoke.mutate(s.id)}>Revoke</Button>}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function ApiKeys() {
  const qc = useQueryClient();
  const keys = useQuery({ queryKey: ["api-keys"], queryFn: api.auth.apiKeys });
  const [name, setName] = useState("");
  const [created, setCreated] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const create = useMutation({
    mutationFn: () => api.auth.createApiKey(name),
    onSuccess: (k) => {
      setCreated(k.key);
      setName("");
      void qc.invalidateQueries({ queryKey: ["api-keys"] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed"),
  });
  const del = useMutation({ mutationFn: (id: string) => api.auth.deleteApiKey(id), onSuccess: () => { toast.success("Key revoked"); void qc.invalidateQueries({ queryKey: ["api-keys"] }); }, onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed") });
  return (
    <Card>
      <CardHeader title="API keys" description="Programmatic access to the REST API (send as `X-API-Key`). Keys are hashed at rest and shown only once." action={<KeyRound className="h-4 w-4 text-muted" />} />
      <div className="mb-4 flex gap-2">
        <Input placeholder="Key name, e.g. CI pipeline" value={name} onChange={(e) => setName(e.target.value)} />
        <Button variant="primary" disabled={!name.trim()} loading={create.isPending} onClick={() => create.mutate()}><Plus className="h-4 w-4" /> Create</Button>
      </div>
      <ul className="divide-y divide-line">
        {keys.data?.map((k) => (
          <li key={k.id} className={cn("flex items-center justify-between gap-3 py-2 text-xs", k.revoked_at && "opacity-50")}>
            <div>
              <p className="font-medium">{k.name} <span className="ml-1 font-mono text-muted">{k.key_prefix}…</span> {k.revoked_at && <Badge className="ml-1">revoked</Badge>}</p>
              <p className="text-muted">created {formatRelative(k.created_at)} · last used {k.last_used_at ? formatRelative(k.last_used_at) : "never"} · scopes {k.scopes.join(", ")}</p>
            </div>
            {!k.revoked_at && <Button size="sm" variant="ghost" onClick={() => confirm("Revoke this key?") && del.mutate(k.id)}><Trash2 className="h-3.5 w-3.5" /></Button>}
          </li>
        ))}
        {keys.data && !keys.data.length && <li className="py-2 text-xs text-muted">No API keys yet.</li>}
      </ul>
      <p className="mt-4 text-xs text-muted">Interactive docs: <a className="text-brand-300 hover:underline" href="/api/v1/docs" target="_blank" rel="noreferrer">/api/v1/docs</a> · OpenAPI JSON: <a className="text-brand-300 hover:underline" href="/api/v1/openapi.json" target="_blank" rel="noreferrer">/api/v1/openapi.json</a></p>
      <Modal open={!!created} onClose={() => setCreated(null)} title="Copy your new API key" footer={<Button variant="primary" onClick={() => setCreated(null)}>Done</Button>}>
        <Alert tone="warning">This is the only time the full key is shown. Store it securely.</Alert>
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-line bg-panel2 p-2 font-mono text-xs">
          <span className="min-w-0 flex-1 break-all">{created}</span>
          <Button size="sm" onClick={() => { void navigator.clipboard.writeText(created!); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>{copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}</Button>
        </div>
      </Modal>
    </Card>
  );
}

function Providers() {
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers.list });
  const kinds: [string, string][] = [["llm", "Language model (research, script, storyboard)"], ["image", "Image generation"], ["video", "Video generation"], ["tts", "Text to speech"], ["stt", "Speech to text (caption alignment)"], ["stock", "Stock media search"]];
  return (
    <div className="space-y-4">
      <Alert tone="info" title="Configured on the server">
        Provider keys never reach the browser. Set <code>LLM_PROVIDER</code>, <code>IMAGE_PROVIDER</code>, <code>VIDEO_PROVIDER</code>, <code>TTS_PROVIDER</code>, <code>STT_PROVIDER</code>, <code>STOCK_PROVIDER</code> and the matching <code>*_API_KEY</code> variables in the backend environment. Mock providers let the whole pipeline run without any keys.
      </Alert>
      <div className="grid gap-4 md:grid-cols-2">
        {kinds.map(([kind, label]) => {
          const active = providers.data?.active?.[kind];
          const list = providers.data?.available?.[kind] ?? [];
          return (
            <Card key={kind}>
              <CardHeader title={label} description={<span>env <code>{kind.toUpperCase()}_PROVIDER={providers.data?.configured_from?.[kind] ?? "…"}</code></span>} action={<Plug className="h-4 w-4 text-muted" />} />
              <ul className="space-y-1.5">
                {list.map((p) => (
                  <li key={p.name} className={cn("flex items-center justify-between rounded-lg border px-3 py-2 text-xs", p.name === active ? "border-brand-500/60 bg-brand-500/10" : "border-line")}>
                    <div>
                      <p className="font-medium">{p.display_name} {p.is_mock && <Badge className="ml-1">mock</Badge>}</p>
                      <p className="text-muted">{p.name}{p.default_model ? ` · ${p.default_model}` : ""}</p>
                    </div>
                    <span className={cn("badge", p.name === active ? "border-brand-500/40 text-brand-200" : p.is_configured ? "border-emerald-500/40 text-emerald-300" : "border-line text-muted")}>{p.name === active ? "active" : p.is_configured ? "configured" : "needs key"}</span>
                  </li>
                ))}
                {!list.length && <li className="text-xs text-muted">{providers.isLoading ? "Loading…" : "No adapters registered."}</li>}
              </ul>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
