"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Coins, LogOut, ChevronRight, Film } from "lucide-react";
import { useAuth } from "@/store/auth";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";

export function Topbar({ compact }: { compact?: boolean }) {
  const { user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const crumbs = pathname.split("/").filter(Boolean);
  return (
    <header className={cn("flex items-center justify-between border-b border-line bg-panel/60 px-4 backdrop-blur", compact ? "h-11" : "h-14 px-6")}>
      <div className="flex items-center gap-2 text-sm text-muted">
        {compact && (
          <Link href="/dashboard" className="mr-2 flex items-center gap-2 font-semibold text-fg">
            <span className="grid h-6 w-6 place-items-center rounded-md bg-brand-500 text-white"><Film className="h-3.5 w-3.5" /></span>
          </Link>
        )}
        {crumbs.slice(0, 3).map((c, i) => (
          <span key={i} className="flex items-center gap-2">
            {i > 0 && <ChevronRight className="h-3 w-3" />}
            <span className={cn(i === crumbs.length - 1 && "text-fg", c.length > 20 && "font-mono text-xs")}>{c.length > 20 ? c.slice(0, 8) : c}</span>
          </span>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <Link href="/billing" className="badge border-amber-500/30 bg-amber-500/10 text-amber-200" title="Credits">
          <Coins className="h-3 w-3" /> {user?.credits_balance ?? 0} credits
        </Link>
        <span className="hidden text-sm text-muted sm:inline">{user?.full_name || user?.email}</span>
        <Button variant="ghost" size="icon" title="Sign out" onClick={async () => { await logout(); router.replace("/login"); }}>
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
