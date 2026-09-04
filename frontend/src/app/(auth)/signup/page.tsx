"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/store/auth";
import { Button, Field, Input, Alert } from "@/components/ui";
import { ApiError } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const signup = useAuth((s) => s.signup);
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (form.password.length < 8) return setError("Password must be at least 8 characters");
    setLoading(true);
    setError(null);
    try {
      await signup(form.email, form.password, form.full_name || undefined);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create account");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card p-6">
      <h1 className="text-lg font-semibold">Create your account</h1>
      <p className="mt-1 text-sm text-muted">Start with 500 free credits — enough for your first videos.</p>
      <form onSubmit={submit} className="mt-6 space-y-4">
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Full name"><Input autoComplete="name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} placeholder="Ada Lovelace" /></Field>
        <Field label="Email"><Input type="email" autoComplete="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="you@example.com" /></Field>
        <Field label="Password" hint="At least 8 characters"><Input type="password" autoComplete="new-password" required minLength={8} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="••••••••" /></Field>
        <Button type="submit" variant="primary" className="w-full" loading={loading}>Create account</Button>
      </form>
      <p className="mt-4 text-center text-xs text-muted">
        Already have an account? <Link href="/login" className="text-brand-300 hover:underline">Sign in</Link>
      </p>
    </div>
  );
}
