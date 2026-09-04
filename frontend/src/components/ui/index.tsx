"use client";
import * as React from "react";
import { Loader2, X, AlertTriangle, Info, CheckCircle2 } from "lucide-react";
import { cn, jobStateColor, JOB_STATE_LABEL, projectStatusColor, PROJECT_STATUS_LABEL } from "@/lib/utils";
import type { JobState, ProjectStatus } from "@/types/api";

/* --------------------------------------------------------------- Button */
type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg" | "icon";
  loading?: boolean;
};
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "secondary", size = "md", loading, children, disabled, ...props },
  ref,
) {
  const v = { primary: "btn-primary", secondary: "btn-secondary", ghost: "btn-ghost", danger: "btn-danger" }[variant];
  const s = { sm: "px-2.5 py-1.5 text-xs", md: "", lg: "px-5 py-3 text-base", icon: "h-8 w-8 p-0" }[size];
  return (
    <button ref={ref} className={cn(v, s, className)} disabled={disabled || loading} {...props}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
});

/* ---------------------------------------------------------------- Inputs */
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...props }, ref) {
  return <input ref={ref} className={cn("input", className)} {...props} />;
});
export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...props }, ref) {
  return <textarea ref={ref} className={cn("input min-h-[80px] resize-y leading-relaxed", className)} {...props} />;
});
export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, children, ...props }, ref) {
  return (
    <select ref={ref} className={cn("input appearance-none bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%238c95b0%22 stroke-width=%222%22><path d=%22m6 9 6 6 6-6%22/></svg>')] bg-[length:12px] bg-[right_10px_center] bg-no-repeat pr-8", className)} {...props}>
      {children}
    </select>
  );
});

export function Field({ label, hint, error, children, className }: { label?: string; hint?: string; error?: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      {label && <label className="label">{label}</label>}
      {children}
      {hint && !error && <p className="mt-1 text-xs text-muted">{hint}</p>}
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  );
}

export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: string; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={checked} disabled={disabled} onClick={() => onChange(!checked)} className={cn("flex items-center gap-2 text-sm", disabled && "opacity-50")}>
      <span className={cn("relative inline-flex h-5 w-9 shrink-0 rounded-full transition", checked ? "bg-brand-500" : "bg-line")}>
        <span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white transition", checked ? "left-[18px]" : "left-0.5")} />
      </span>
      {label && <span>{label}</span>}
    </button>
  );
}

export function Slider({ value, min, max, step = 0.01, onChange, className }: { value: number; min: number; max: number; step?: number; onChange: (v: number) => void; className?: string }) {
  return <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(parseFloat(e.target.value))} className={cn("h-1.5 w-full cursor-pointer appearance-none rounded-full bg-line accent-brand-500", className)} />;
}

/* --------------------------------------------------------------- Badges */
export function Badge({ className, children }: { className?: string; children: React.ReactNode }) {
  return <span className={cn("badge border-line bg-panel2 text-muted", className)}>{children}</span>;
}
export function JobStateBadge({ state, className }: { state: JobState | string; className?: string }) {
  const active = !["COMPLETED", "FAILED", "CANCELLED", "QUEUED"].includes(state);
  return (
    <span className={cn("badge", jobStateColor(state), className)}>
      {active && <span className="h-1.5 w-1.5 animate-pulseSoft rounded-full bg-current" />}
      {JOB_STATE_LABEL[state as JobState] ?? state}
    </span>
  );
}
export function ProjectStatusBadge({ status, className }: { status: ProjectStatus | string; className?: string }) {
  return <span className={cn("badge", projectStatusColor(status), className)}>{PROJECT_STATUS_LABEL[status as ProjectStatus] ?? status}</span>;
}

/* ------------------------------------------------------------- Progress */
export function ProgressBar({ value, className, tone = "brand", animated }: { value: number; className?: string; tone?: "brand" | "green" | "red"; animated?: boolean }) {
  const color = { brand: "bg-brand-500", green: "bg-emerald-500", red: "bg-red-500" }[tone];
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-line", className)}>
      <div className={cn("h-full rounded-full transition-all duration-500", color, animated && "animate-pulseSoft")} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  );
}

/* ---------------------------------------------------------------- Cards */
export function Card({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("card p-5", className)} {...props}>
      {children}
    </div>
  );
}
export function CardHeader({ title, description, action, className }: { title: React.ReactNode; description?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("mb-4 flex items-start justify-between gap-4", className)}>
      <div>
        <h3 className="text-sm font-semibold">{title}</h3>
        {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}
export function Stat({ label, value, sub, icon }: { label: string; value: React.ReactNode; sub?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <Card className="flex items-start justify-between">
      <div>
        <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
        {sub && <p className="mt-1 text-xs text-muted">{sub}</p>}
      </div>
      {icon && <div className="rounded-lg bg-brand-500/10 p-2 text-brand-300">{icon}</div>}
    </Card>
  );
}

/* ------------------------------------------------------------ Feedback */
export function Alert({ tone = "info", title, children, className }: { tone?: "info" | "warning" | "error" | "success"; title?: string; children?: React.ReactNode; className?: string }) {
  const map = {
    info: ["border-brand-500/30 bg-brand-500/10 text-brand-100", Info],
    warning: ["border-amber-500/30 bg-amber-500/10 text-amber-100", AlertTriangle],
    error: ["border-red-500/30 bg-red-500/10 text-red-100", AlertTriangle],
    success: ["border-emerald-500/30 bg-emerald-500/10 text-emerald-100", CheckCircle2],
  } as const;
  const [cls, Icon] = map[tone];
  return (
    <div className={cn("flex gap-3 rounded-lg border p-3 text-sm", cls, className)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={cn(title && "mt-0.5", "text-[13px] opacity-90")}>{children}</div>}
      </div>
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-5 w-5 animate-spin text-muted", className)} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton h-4 w-full", className)} />;
}

export function EmptyState({ icon, title, description, action, className }: { icon?: React.ReactNode; title: string; description?: string; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("card flex flex-col items-center justify-center px-6 py-12 text-center", className)}>
      {icon && <div className="mb-3 rounded-xl bg-panel2 p-3 text-muted">{icon}</div>}
      <h3 className="text-sm font-semibold">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-xs text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/* ---------------------------------------------------------------- Modal */
export function Modal({ open, onClose, title, children, footer, size = "md" }: { open: boolean; onClose: () => void; title?: React.ReactNode; children: React.ReactNode; footer?: React.ReactNode; size?: "sm" | "md" | "lg" | "xl" }) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  const w = { sm: "max-w-sm", md: "max-w-lg", lg: "max-w-2xl", xl: "max-w-4xl" }[size];
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onMouseDown={onClose}>
      <div className={cn("card w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl", w)} onMouseDown={(e) => e.stopPropagation()}>
        {title && (
          <div className="flex items-center justify-between border-b border-line px-5 py-3">
            <h3 className="text-sm font-semibold">{title}</h3>
            <button onClick={onClose} className="btn-ghost h-7 w-7 p-0">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- Tabs */
export function Tabs<T extends string>({ tabs, value, onChange, className }: { tabs: { id: T; label: React.ReactNode; count?: number }[]; value: T; onChange: (v: T) => void; className?: string }) {
  return (
    <div className={cn("flex gap-1 rounded-lg border border-line bg-panel p-1", className)}>
      {tabs.map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)} className={cn("flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition", value === t.id ? "bg-panel2 text-fg shadow" : "text-muted hover:text-fg")}>
          {t.label}
          {t.count != null && <span className="ml-1.5 rounded bg-line px-1 text-[10px] text-muted">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function PageHeader({ title, description, actions, className }: { title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("mb-6 flex flex-wrap items-end justify-between gap-4", className)}>
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="rounded border border-line bg-panel2 px-1.5 py-0.5 font-mono text-[10px] text-muted">{children}</kbd>;
}
