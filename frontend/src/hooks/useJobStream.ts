"use client";
import { useEffect, useRef, useState } from "react";
import { sseUrl } from "@/lib/api";
import type { ProgressEvent } from "@/types/api";
import { isTerminal } from "@/lib/utils";

interface Options {
  enabled?: boolean;
  onEvent?: (e: ProgressEvent) => void;
  onDone?: (e: ProgressEvent | null) => void;
}

/**
 * Subscribe to an SSE channel. Paths: `/jobs/{id}/events`, `/jobs/projects/{pid}/events`, `/jobs/events`.
 * Reconnects with backoff while the tab is open; the browser EventSource keeps the token in the query string
 * (short-lived access JWT) because EventSource cannot send Authorization headers.
 */
export function useEventStream(path: string | null, { enabled = true, onEvent, onDone }: Options = {}) {
  const [last, setLast] = useState<ProgressEvent | null>(null);
  const [connected, setConnected] = useState(false);
  const handlers = useRef({ onEvent, onDone });
  handlers.current = { onEvent, onDone };

  useEffect(() => {
    if (!path || !enabled) return;
    let es: EventSource | null = null;
    let closed = false;
    let retry = 1000;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const open = () => {
      if (closed) return;
      es = new EventSource(sseUrl(path));
      es.onopen = () => {
        setConnected(true);
        retry = 1000;
      };
      es.onmessage = (m) => {
        try {
          const ev = JSON.parse(m.data) as ProgressEvent;
          setLast(ev);
          handlers.current.onEvent?.(ev);
        } catch {
          /* heartbeat / comment */
        }
      };
      es.addEventListener("done", (m) => {
        let ev: ProgressEvent | null = null;
        try {
          ev = JSON.parse((m as MessageEvent).data) as ProgressEvent;
          if (ev) setLast(ev);
        } catch {
          /* no payload */
        }
        closed = true;
        es?.close();
        setConnected(false);
        handlers.current.onDone?.(ev);
      });
      es.onerror = () => {
        setConnected(false);
        es?.close();
        if (closed) return;
        timer = setTimeout(open, retry);
        retry = Math.min(retry * 2, 15000);
      };
    };
    open();
    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      es?.close();
      setConnected(false);
    };
  }, [path, enabled]);

  return { last, connected, done: last ? isTerminal(last.state) : false };
}

/** Stream progress for a single job. Closes automatically when the job reaches a terminal state. */
export function useJobStream(jobId: string | null | undefined, opts: Options = {}) {
  return useEventStream(jobId ? `/jobs/${jobId}/events` : null, opts);
}

/** Stream all job events for a project (pipeline + render). */
export function useProjectStream(projectId: string | null | undefined, opts: Options = {}) {
  return useEventStream(projectId ? `/jobs/projects/${projectId}/events` : null, opts);
}

/** Stream every job event for the signed-in user (dashboard). */
export function useUserStream(opts: Options = {}) {
  return useEventStream(`/jobs/events`, opts);
}
