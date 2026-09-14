import type { AnalysisView, ClusterStatus, EventLine, LogLine } from "./types";

async function parse<T>(response: Response): Promise<T> {
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.error || response.statusText);
  }
  return data as T;
}

export function fetchStatus(signal?: AbortSignal): Promise<ClusterStatus> {
  return fetch("/api/status", { signal }).then((res) => parse<ClusterStatus>(res));
}

export function fetchLogs(source: string, signal?: AbortSignal): Promise<{ logs: LogLine[] }> {
  return fetch(`/api/logs?source=${encodeURIComponent(source)}`, { signal }).then((res) =>
    parse<{ logs: LogLine[] }>(res),
  );
}

export function fetchEvents(signal?: AbortSignal): Promise<{ events: EventLine[] }> {
  return fetch("/api/events", { signal }).then((res) => parse<{ events: EventLine[] }>(res));
}

export function fetchRecommendation(signal?: AbortSignal): Promise<AnalysisView | null> {
  return fetch("/api/recommendations", { signal }).then((res) => {
    if (res.status === 404) return null;
    return parse<AnalysisView>(res);
  });
}

export function startIncident(mode: string): Promise<unknown> {
  return fetch("/api/demo/incidents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  }).then((res) => parse(res));
}

export function executeRecommendation(id?: string): Promise<AnalysisView> {
  return fetch("/api/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  }).then((res) => parse<AnalysisView>(res));
}

export function fetchPod(namespace: string, name: string): Promise<Record<string, unknown>> {
  return fetch(`/api/pods/${namespace}/${name}`).then((res) => parse(res));
}
