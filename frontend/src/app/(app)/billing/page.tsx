"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Coins, Check, CreditCard, Clock3, HardDrive, Film, Receipt, ArrowUpRight } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/store/auth";
import { Alert, Button, Card, CardHeader, Modal, PageHeader, ProgressBar, Select, Stat, Tabs } from "@/components/ui";
import { cn, formatBytes, formatDate, titleCase } from "@/lib/utils";

export default function BillingPage() {
  const qc = useQueryClient();
  const { user, refreshUser } = useAuth();
  const [period, setPeriod] = useState<string>(new Date().toISOString().slice(0, 7));
  const [tab, setTab] = useState<"usage" | "ledger" | "records">("usage");
  const [buyOpen, setBuyOpen] = useState(false);
  const [credits, setCredits] = useState(500);
  const summary = useQuery({ queryKey: ["usage", "summary", period], queryFn: () => api.usage.summary(period) });
  const perProject = useQuery({ queryKey: ["usage", "projects", period], queryFn: () => api.usage.projects(period) });
  const ledger = useQuery({ queryKey: ["usage", "ledger"], queryFn: () => api.usage.credits({ page_size: 50 }), enabled: tab === "ledger" });
  const records = useQuery({ queryKey: ["usage", "records"], queryFn: () => api.usage.records({ page_size: 100 }), enabled: tab === "records" });
  const plans = useQuery({ queryKey: ["billing", "plans"], queryFn: api.billing.plans });
  const sub = useQuery({ queryKey: ["billing", "subscription"], queryFn: api.billing.subscription });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["billing"] });
    void qc.invalidateQueries({ queryKey: ["usage"] });
    void refreshUser();
  };
  const checkout = useMutation({
    mutationFn: (plan: string) => api.billing.checkout(plan, `${window.location.origin}/billing?success=1`, `${window.location.origin}/billing`),
    onSuccess: (r) => {
      if (r.mode === "stripe" && r.checkout_url) window.location.href = r.checkout_url;
      else {
        toast.success(r.message);
        invalidate();
      }
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Checkout failed"),
  });
  const cancel = useMutation({ mutationFn: api.billing.cancel, onSuccess: () => { toast.success("Subscription will end at period close"); invalidate(); }, onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed") });
  const buy = useMutation({
    mutationFn: () => api.billing.buyCredits(credits),
    onSuccess: (r) => {
      if (r.mode === "stripe" && r.checkout_url) window.location.href = r.checkout_url;
      else {
        toast.success(r.message);
        setBuyOpen(false);
        invalidate();
      }
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Purchase failed"),
  });
  const portal = useMutation({ mutationFn: api.billing.portal, onSuccess: (m) => (m.message.startsWith("http") ? (window.location.href = m.message) : toast(m.message)), onError: (e) => toast.error(e instanceof ApiError ? e.message : "Failed") });

  const s = summary.data;
  const periods = Array.from({ length: 6 }, (_, i) => {
    const d = new Date();
    d.setMonth(d.getMonth() - i);
    return d.toISOString().slice(0, 7);
  });
  const maxDaily = Math.max(1, ...(s?.daily.map((d) => d.credits) ?? [1]));

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Billing & usage" description="Credits, subscription and a full record of what each generation cost." actions={<><Select className="w-36" value={period} onChange={(e) => setPeriod(e.target.value)}>{periods.map((p) => <option key={p}>{p}</option>)}</Select><Button variant="primary" onClick={() => setBuyOpen(true)}><Coins className="h-4 w-4" /> Buy credits</Button></>} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Credits balance" value={user?.credits_balance ?? "…"} sub={s ? `${s.credits_used} used · ${s.credits_granted} granted in ${s.period}` : undefined} icon={<Coins className="h-5 w-5" />} />
        <Stat label="Render minutes" value={s ? s.render_minutes.toFixed(1) : "…"} sub="this period" icon={<Clock3 className="h-5 w-5" />} />
        <Stat label="Videos completed" value={s?.videos_completed ?? "…"} icon={<Film className="h-5 w-5" />} />
        <Stat label="Storage" value={s ? formatBytes(s.storage_used_bytes) : "…"} sub={s ? `of ${formatBytes(s.storage_limit_bytes, 0)}` : undefined} icon={<HardDrive className="h-5 w-5" />} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <Tabs value={tab} onChange={setTab} tabs={[{ id: "usage", label: "Usage breakdown" }, { id: "ledger", label: "Credit ledger" }, { id: "records", label: "Usage records" }]} className="mb-4 max-w-lg" />
            {tab === "usage" && s && (
              <div className="space-y-6">
                <div>
                  <p className="label">Daily credits</p>
                  <div className="flex h-28 items-end gap-1">
                    {s.daily.length ? s.daily.map((d) => (
                      <div key={d.day} className="group relative flex-1">
                        <div className="w-full rounded-t bg-brand-500/70 transition group-hover:bg-brand-400" style={{ height: `${Math.max(2, (d.credits / maxDaily) * 100)}px` }} />
                        <span className="pointer-events-none absolute -top-6 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded bg-panel2 px-1.5 py-0.5 text-[10px] group-hover:block">{d.day.slice(5)} · {d.credits} cr</span>
                      </div>
                    )) : <p className="text-xs text-muted">No usage in this period.</p>}
                  </div>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <p className="label">By kind</p>
                    <ul className="space-y-2">
                      {Object.entries(s.by_kind).sort((a, b) => b[1].credits - a[1].credits).map(([k, v]) => (
                        <li key={k}>
                          <div className="flex justify-between text-xs"><span>{titleCase(k)}</span><span className="tabular-nums text-muted">{Number(v.quantity.toFixed(1)).toLocaleString()} {v.unit} · <span className="text-fg">{v.credits} cr</span></span></div>
                          <ProgressBar value={s.credits_used ? (v.credits / s.credits_used) * 100 : 0} className="mt-1" />
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="label">By project</p>
                    <ul className="divide-y divide-line text-xs">
                      {perProject.data?.map((r) => (
                        <li key={r.project_id ?? "none"} className="flex justify-between py-1.5"><span className="truncate">{r.title ?? "—"}</span><span className="tabular-nums">{r.credits} cr</span></li>
                      ))}
                      {perProject.data && !perProject.data.length && <li className="py-1.5 text-muted">No project usage yet.</li>}
                    </ul>
                  </div>
                </div>
              </div>
            )}
            {tab === "ledger" && (
              <table className="w-full text-xs">
                <thead><tr className="text-left text-muted"><th className="py-1 font-medium">When</th><th className="font-medium">Type</th><th className="font-medium">Description</th><th className="text-right font-medium">Amount</th><th className="text-right font-medium">Balance</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {ledger.data?.items.map((t) => (
                    <tr key={t.id}><td className="py-1.5 text-muted">{formatDate(t.created_at)}</td><td>{titleCase(t.kind)}</td><td className="max-w-xs truncate">{t.description}</td><td className={cn("text-right tabular-nums", t.amount < 0 ? "text-red-300" : "text-emerald-300")}>{t.amount > 0 ? "+" : ""}{t.amount}</td><td className="text-right tabular-nums">{t.balance_after}</td></tr>
                  ))}
                  {ledger.data && !ledger.data.items.length && <tr><td colSpan={5} className="py-3 text-muted">No transactions.</td></tr>}
                </tbody>
              </table>
            )}
            {tab === "records" && (
              <table className="w-full text-xs">
                <thead><tr className="text-left text-muted"><th className="py-1 font-medium">When</th><th className="font-medium">Kind</th><th className="font-medium">Provider</th><th className="text-right font-medium">Quantity</th><th className="text-right font-medium">Credits</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {records.data?.items.map((r) => (
                    <tr key={r.id}><td className="py-1.5 text-muted">{formatDate(r.created_at)}</td><td>{titleCase(r.kind)}</td><td className="font-mono">{r.provider ?? "—"}{r.model ? ` / ${r.model}` : ""}</td><td className="text-right tabular-nums">{Number(r.quantity.toFixed(2))} {r.unit}</td><td className="text-right tabular-nums">{r.credits}</td></tr>
                  ))}
                  {records.data && !records.data.items.length && <tr><td colSpan={5} className="py-3 text-muted">No records.</td></tr>}
                </tbody>
              </table>
            )}
          </Card>

          <Card>
            <CardHeader title="Plans" description="Stripe-ready: with STRIPE_* keys configured, checkout redirects to Stripe; otherwise plan changes apply instantly in manual mode." />
            <div className="grid gap-3 md:grid-cols-3">
              {plans.data?.map((pl) => (
                <div key={pl.id} className={cn("rounded-xl border p-4", pl.is_current ? "border-brand-500 bg-brand-500/5" : "border-line")}>
                  <div className="flex items-center justify-between"><p className="font-semibold">{pl.name}</p>{pl.is_current && <span className="badge border-brand-500/40 bg-brand-500/10 text-brand-200">current</span>}</div>
                  <p className="mt-1 text-2xl font-semibold">${pl.price_usd_month}<span className="text-sm font-normal text-muted">/mo</span></p>
                  <ul className="mt-3 space-y-1 text-xs text-muted">
                    <li className="flex gap-2"><Check className="h-3.5 w-3.5 text-emerald-300" /> {pl.monthly_credits.toLocaleString()} credits / month</li>
                    <li className="flex gap-2"><Check className="h-3.5 w-3.5 text-emerald-300" /> {pl.storage_gb} GB storage</li>
                    <li className="flex gap-2"><Check className="h-3.5 w-3.5 text-emerald-300" /> up to {pl.max_video_minutes} min videos · {pl.max_resolution}</li>
                    <li className="flex gap-2"><Check className="h-3.5 w-3.5 text-emerald-300" /> {pl.concurrent_renders} concurrent render{pl.concurrent_renders > 1 ? "s" : ""}{pl.watermark ? " · watermark" : " · no watermark"}</li>
                    {pl.features.map((f) => <li key={f} className="flex gap-2"><Check className="h-3.5 w-3.5 text-emerald-300" /> {f}</li>)}
                  </ul>
                  {!pl.is_current && <Button className="mt-4 w-full" variant={pl.price_usd_month > 0 ? "primary" : "secondary"} loading={checkout.isPending && checkout.variables === pl.id} onClick={() => checkout.mutate(pl.id)}>{pl.price_usd_month > 0 ? "Upgrade" : "Switch"} <ArrowUpRight className="h-4 w-4" /></Button>}
                </div>
              ))}
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Subscription" action={<CreditCard className="h-4 w-4 text-muted" />} />
            {sub.data ? (
              <dl className="grid grid-cols-2 gap-y-2 text-xs">
                <dt className="text-muted">Plan</dt><dd className="font-medium capitalize">{sub.data.plan}</dd>
                <dt className="text-muted">Status</dt><dd className="capitalize">{sub.data.status}{sub.data.cancel_at_period_end && " · cancels at period end"}</dd>
                <dt className="text-muted">Monthly credits</dt><dd>{sub.data.monthly_credits.toLocaleString()}</dd>
                <dt className="text-muted">Period</dt><dd>{sub.data.current_period_start ? `${new Date(sub.data.current_period_start).toLocaleDateString()} → ${sub.data.current_period_end ? new Date(sub.data.current_period_end).toLocaleDateString() : "—"}` : "—"}</dd>
                <dt className="text-muted">Payment</dt><dd>{sub.data.payment_provider ?? "manual"}</dd>
              </dl>
            ) : <p className="text-sm text-muted">Loading…</p>}
            <div className="mt-4 flex flex-col gap-2">
              <Button size="sm" onClick={() => portal.mutate()} loading={portal.isPending}><Receipt className="h-4 w-4" /> Billing portal / invoices</Button>
              {sub.data && sub.data.plan !== "free" && !sub.data.cancel_at_period_end && <Button size="sm" variant="ghost" onClick={() => confirm("Cancel at the end of the current period?") && cancel.mutate()}>Cancel subscription</Button>}
            </div>
          </Card>
          <Card>
            <CardHeader title="Credit costs" description="How credits are consumed." />
            <ul className="space-y-1 text-xs text-muted">
              <li className="flex justify-between"><span>Research run</span><span>5</span></li>
              <li className="flex justify-between"><span>Script</span><span>2 / minute</span></li>
              <li className="flex justify-between"><span>Voiceover</span><span>3 / 1,000 characters</span></li>
              <li className="flex justify-between"><span>AI image</span><span>4</span></li>
              <li className="flex justify-between"><span>AI video clip</span><span>25</span></li>
              <li className="flex justify-between"><span>Rendering</span><span>6 / output minute</span></li>
            </ul>
            <Alert tone="info" className="mt-3">Preview renders are free. Failed stages are refunded automatically.</Alert>
          </Card>
        </div>
      </div>

      <Modal open={buyOpen} onClose={() => setBuyOpen(false)} title="Buy credits" footer={<><Button onClick={() => setBuyOpen(false)}>Cancel</Button><Button variant="primary" loading={buy.isPending} onClick={() => buy.mutate()}><Coins className="h-4 w-4" /> Buy {credits.toLocaleString()} credits</Button></>}>
        <div className="grid grid-cols-4 gap-2">
          {[500, 1000, 2500, 5000].map((c) => (
            <button key={c} onClick={() => setCredits(c)} className={cn("rounded-lg border p-3 text-center", credits === c ? "border-brand-500 bg-brand-500/10" : "border-line")}>
              <p className="font-semibold">{c.toLocaleString()}</p>
              <p className="text-[11px] text-muted">${(c / 100).toFixed(0)}</p>
            </button>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted">With Stripe configured you will be redirected to a secure checkout; in manual/dev mode credits are granted immediately.</p>
      </Modal>
    </div>
  );
}
