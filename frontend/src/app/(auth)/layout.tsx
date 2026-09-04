import Link from "next/link";
import { Film } from "lucide-react";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden px-4">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(58,95,255,0.2),transparent_60%)]" />
      <div className="relative w-full max-w-md">
        <Link href="/" className="mb-8 flex items-center justify-center gap-2 font-semibold">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-500 text-white shadow-glow"><Film className="h-4 w-4" /></span>
          LongForm AI
        </Link>
        {children}
      </div>
    </main>
  );
}
