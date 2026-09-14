import type { AnalysisView, ClusterStatus, EventLine, LogLine } from "./types";

async function parse<T>(response: Response): Promise<T> {
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.error || response.statusText);
  }
  return data as T;
}

export function fetchStatus(): Promise<ClusterStatus> {
  return fetch("/api/status").then((res) => parse<ClusterStatus>(res));
}

export function fetchLogs(source: string): Promise<{ logs: LogLine[] }> {
  return fetch(`/api/logs?source=${encodeURIComponent(source)}`).then((res) =>
    parse<{ logs: LogLine[] }>(res),
  );
}

export function fetchEvents(): Promise<{ events: EventLine[] }> {
  return fetch("/api/events").then((res) => parse<{ events: EventLine[] }>(res));
}

export function fetchRecommendation(): Promise<AnalysisView | null> {
  return fetch("/api/recommendations").then((res) => {
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
