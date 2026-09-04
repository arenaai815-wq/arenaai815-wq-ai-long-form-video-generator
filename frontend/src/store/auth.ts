"use client";
import { create } from "zustand";
import { api, tokens, ApiError } from "@/lib/api";
import type { User } from "@/types/api";

interface AuthState {
  user: User | null;
  status: "idle" | "loading" | "authenticated" | "anonymous";
  load: () => Promise<User | null>;
  login: (email: string, password: string) => Promise<User>;
  signup: (email: string, password: string, fullName?: string) => Promise<User>;
  logout: () => Promise<void>;
  setUser: (u: User | null) => void;
  refreshUser: () => Promise<void>;
}

export const useAuth = create<AuthState>((set, get) => ({
  user: null,
  status: "idle",
  setUser: (user) => set({ user, status: user ? "authenticated" : "anonymous" }),
  async load() {
    if (!tokens.access && !tokens.refresh) {
      set({ status: "anonymous", user: null });
      return null;
    }
    set({ status: "loading" });
    try {
      const user = await api.auth.me();
      set({ user, status: "authenticated" });
      return user;
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) tokens.set(null);
      set({ user: null, status: "anonymous" });
      return null;
    }
  },
  async login(email, password) {
    const pair = await api.auth.login(email, password);
    tokens.set(pair);
    const user = await api.auth.me();
    set({ user, status: "authenticated" });
    return user;
  },
  async signup(email, password, fullName) {
    const pair = await api.auth.signup(email, password, fullName);
    tokens.set(pair);
    const user = await api.auth.me();
    set({ user, status: "authenticated" });
    return user;
  },
  async logout() {
    try {
      await api.auth.logout();
    } catch {
      /* ignore */
    }
    tokens.set(null);
    set({ user: null, status: "anonymous" });
  },
  async refreshUser() {
    if (get().status !== "authenticated") return;
    try {
      set({ user: await api.auth.me() });
    } catch {
      /* ignore */
    }
  },
}));
