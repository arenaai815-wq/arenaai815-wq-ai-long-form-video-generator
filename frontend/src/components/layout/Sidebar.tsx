"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, FolderKanban, PlusCircle, Library, Settings, CreditCard, Film, Activity } from "lucide-react";
import { cn } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatBytes } from "@/lib/utils";

const nav = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/projects/new", label: "New project", icon: PlusCircle },
  { href: "/media", label: "Media library", icon: Library },
  { href: "/jobs", label: "Jobs & workers", icon: Activity },
  { href: "/billing", label: "Billing & usage", icon: CreditCard },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const storage = useQuery({ queryKey: ["storage"], queryFn: api.media.storage, staleTime: 60_000 });
  const pct = storage.data ? Math.min(100, (storage.data.used_bytes / Math.max(1, storage.data.limit_bytes)) * 100) : 0;
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-line bg-panel md:flex">
      <Link href="/dashboard" className="flex items-center gap-2 px-5 py-5 font-semibold">
        <span className="grid h-7 w-7 place-items-center rounded-lg bg-brand-500 text-white shadow-glow"><Film className="h-4 w-4" /></span>
        LongForm AI
      </Link>
      <nav className="flex-1 space-y-0.5 px-3">
        {nav.map((n) => {
          const active = n.href === "/projects" ? pathname === "/projects" || (pathname.startsWith("/projects/") && pathname !== "/projects/new") : pathname.startsWith(n.href);
          return (
            <Link key={n.href} href={n.href} className={cn("flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition", active ? "bg-brand-500/15 text-brand-100" : "text-muted hover:bg-panel2 hover:text-fg")}>
              <n.icon className="h-4 w-4" />
              {n.label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-line p-4">
        <div className="flex items-center justify-between text-xs text-muted">
          <span>Storage</span>
          <span>{storage.data ? `${formatBytes(storage.data.used_bytes)} / ${formatBytes(storage.data.limit_bytes, 0)}` : "…"}</span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-line"><div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} /></div>
      </div>
    </aside>
  );
}
