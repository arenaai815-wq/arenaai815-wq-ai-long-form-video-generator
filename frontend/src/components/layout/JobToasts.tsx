"use client";
import { useRef } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { useUserStream } from "@/hooks/useJobStream";
import { useAuth } from "@/store/auth";
import { titleCase } from "@/lib/utils";

/** Global listener: surfaces job completions/failures as toasts and invalidates caches. */
export function JobToasts() {
  const qc = useQueryClient();
  const refreshUser = useAuth((s) => s.refreshUser);
  const seen = useRef(new Map<string, string>());
  useUserStream({
    onEvent: (ev) => {
      const prev = seen.current.get(ev.job_id);
      if (prev === ev.state) return;
      seen.current.set(ev.job_id, ev.state);
      const label = titleCase(ev.job_type);
      if (ev.state === "COMPLETED") {
        toast.success(`${label} finished`, { description: ev.message });
        void refreshUser();
      } else if (ev.state === "FAILED") {
        toast.error(`${label} failed`, { description: ev.error || ev.message });
      } else if (ev.state === "CANCELLED") {
        toast(`${label} cancelled`);
      }
      // keep every project view fresh without polling
      void qc.invalidateQueries({ queryKey: ["project", ev.project_id] });
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: ["jobs"] });
      if (ev.state === "COMPLETED" || ev.state === "FAILED") {
        ["research", "script", "scenes", "captions", "timeline", "renders", "voiceovers", "media", "storage", "usage"].forEach((k) => void qc.invalidateQueries({ queryKey: [k] }));
      }
    },
  });
  return null;
}
