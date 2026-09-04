"use client";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/store/auth";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { Spinner } from "@/components/ui";
import { JobToasts } from "@/components/layout/JobToasts";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { status, load } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "idle") void load();
  }, [status, load]);

  useEffect(() => {
    if (status === "anonymous") router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [status, router, pathname]);

  useEffect(() => {
    const onAuth = () => void load();
    window.addEventListener("lf:auth", onAuth);
    return () => window.removeEventListener("lf:auth", onAuth);
  }, [load]);

  if (status !== "authenticated") {
    return (
      <div className="grid min-h-screen place-items-center">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  const isEditor = /\/projects\/[^/]+\/editor/.test(pathname);
  return (
    <div className="flex h-screen overflow-hidden">
      {!isEditor && <Sidebar />}
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar compact={isEditor} />
        <main className={isEditor ? "min-h-0 flex-1 overflow-hidden" : "min-h-0 flex-1 overflow-y-auto px-6 py-6"}>{children}</main>
      </div>
      <JobToasts />
    </div>
  );
}
