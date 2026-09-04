"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useProjectStream } from "@/hooks/useJobStream";
import type { ProgressEvent } from "@/types/api";
import { useCallback, useRef, useState } from "react";

/**
 * Loads a project and keeps it (and its stage data) fresh from the project SSE channel.
 * Returns the latest live event per job so pages can show inline progress without polling.
 */
export function useProject(projectId: string) {
  const qc = useQueryClient();
  const project = useQuery({ queryKey: ["project", projectId], queryFn: () => api.projects.get(projectId), enabled: !!projectId });
  const [live, setLive] = useState<Record<string, ProgressEvent>>({});
  const lastState = useRef<Record<string, string>>({});

  const onEvent = useCallback(
    (ev: ProgressEvent) => {
      setLive((m) => ({ ...m, [ev.job_id]: ev }));
      const prev = lastState.current[ev.job_id];
      lastState.current[ev.job_id] = ev.state;
      const changed = prev !== ev.state;
      const terminal = ["COMPLETED", "FAILED", "CANCELLED"].includes(ev.state);
      if (changed || terminal) {
        void qc.invalidateQueries({ queryKey: ["project", projectId] });
        void qc.invalidateQueries({ queryKey: ["jobs"] });
      }
      if (terminal) {
        ["research", "script", "scenes", "captions", "timeline", "renders", "voiceovers", "media"].forEach((k) => void qc.invalidateQueries({ queryKey: [k, projectId] }));
      }
      // stage transitions inside the pipeline: refresh the artefact that was just produced
      if (changed && ev.result?.completed_stages) {
        ["research", "script", "scenes", "captions", "timeline"].forEach((k) => void qc.invalidateQueries({ queryKey: [k, projectId] }));
      }
    },
    [projectId, qc],
  );
  useProjectStream(projectId, { onEvent });

  const activeJobs = Object.values(live).filter((e) => !["COMPLETED", "FAILED", "CANCELLED"].includes(e.state));
  return { project, live, activeJobs, activeJob: project.data?.active_job ?? null };
}
