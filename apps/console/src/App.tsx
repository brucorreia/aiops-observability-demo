import { useCallback, useEffect, useState } from "react";
import {
  executeRecommendation,
  fetchEvents,
  fetchLogs,
  fetchPod,
  fetchRecommendation,
  fetchStatus,
  startIncident,
} from "./api";
import { Drawer } from "./Drawer";
import { IncidentPanel } from "./Incident";
import { LiveApp } from "./LiveApp";
import { Logs } from "./Logs";
import { Metrics } from "./Metrics";
import { TopBar } from "./TopBar";
import { Topology } from "./Topology";
import { Workloads } from "./Workloads";
import type { AnalysisView, ClusterStatus, EventLine, LogLine, Workload } from "./types";

function isProblematic(item: Workload | null): boolean {
  if (!item) return false;
  return (
    !item.ready ||
    item.status === "CrashLoopBackOff" ||
    item.status === "OOMKilled" ||
    item.reason === "OOMKilled" ||
    item.reason === "Error"
  );
}

export default function App() {
  const [status, setStatus] = useState<ClusterStatus | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisView | null>(null);
  const [demoLogs, setDemoLogs] = useState<LogLine[]>([]);
  const [agentLogs, setAgentLogs] = useState<LogLine[]>([]);
  const [events, setEvents] = useState<EventLine[]>([]);
  const [paused, setPaused] = useState(false);
  const [pollError, setPollError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Workload | null>(null);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [appKey, setAppKey] = useState(0);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const [nextStatus, nextAnalysis, nextDemo, nextAgent, nextEvents] = await Promise.all([
        fetchStatus(signal),
        fetchRecommendation(signal),
        fetchLogs("demo-app", signal),
        fetchLogs("ai-agent", signal),
        fetchEvents(signal),
      ]);
      setStatus(nextStatus);
      setAnalysis(nextAnalysis);
      setDemoLogs(nextDemo.logs || []);
      setAgentLogs(nextAgent.logs || []);
      setEvents(nextEvents.events || []);
      setPollError(null);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setPollError(err instanceof Error ? err.message : "falha ao ler o cluster");
    }
  }, []);

  useEffect(() => {
    if (paused) return;
    let controller: AbortController | null = null;
    const tick = () => {
      controller?.abort();
      controller = new AbortController();
      refresh(controller.signal);
    };
    tick();
    const timer = window.setInterval(tick, 2500);
    return () => {
      controller?.abort();
      window.clearInterval(timer);
    };
  }, [paused, refresh]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    fetchPod(selected.namespace, selected.name)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [selected]);

  function selectWorkload(item: Workload) {
    setSelected((current) =>
      current?.namespace === item.namespace && current?.name === item.name ? null : item,
    );
  }

  async function onIncident(mode: string) {
    if (status?.pipeline?.busy) {
      setError(
        status.pipeline.message ||
          "Pipeline em andamento. Nova ação só será possível depois do término.",
      );
      return;
    }
    setBusy(mode === "good" ? "Restaurando a demo-app…" : "Disparando CrashLoop via GitOps…");
    setError(null);
    setSelected(null);
    try {
      await startIncident(mode);
      setAppKey((value) => value + 1);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "falha ao commitar o incidente");
    } finally {
      setBusy(null);
    }
  }

  async function onExecute() {
    if (!analysis) return;
    setActionError(null);
    setBusy("Aplicando a ação da IA…");
    try {
      const updated = await executeRecommendation(analysis.id);
      setAnalysis(updated);
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "falha ao executar");
    } finally {
      setBusy(null);
    }
  }

  const showAi = isProblematic(selected);

  return (
    <div className="relative flex h-screen flex-col overflow-hidden">
      <TopBar
        status={status}
        paused={paused}
        busy={busy}
        error={error || pollError}
        pipelineLocked={Boolean(status?.pipeline?.busy)}
        pipelineMessage={status?.pipeline?.busy ? status.pipeline.message : null}
        onTogglePause={() => setPaused((value) => !value)}
        onIncident={onIncident}
      />
      {status ? <Metrics status={status} /> : <div className="px-6 py-4 text-sm text-mute">Lendo o cluster…</div>}
      <div className="flex min-h-0 flex-1">
        <main className="grid min-h-0 min-w-0 flex-1 grid-cols-[minmax(0,1.1fr)_minmax(0,0.95fr)] grid-rows-[minmax(0,1.05fr)_minmax(0,0.95fr)] gap-3 p-4 pr-3">
          <LiveApp reloadKey={appKey} fallbackOrder={status?.demo_app?.api} />
          <Topology
            nodes={status?.topology.nodes || []}
            unscheduled={status?.topology.unscheduled || []}
            selected={selected}
            onSelect={selectWorkload}
          />
          <Workloads items={status?.workloads || []} selected={selected} onSelect={selectWorkload} />
          <Logs demo={demoLogs} agent={agentLogs} />
        </main>
        {showAi ? (
          <IncidentPanel
            analysis={analysis}
            workload={selected}
            timeline={status?.timeline || []}
            events={events}
            busy={Boolean(busy)}
            error={actionError}
            automaticExecution={Boolean(status?.automatic_execution_allowed)}
            onExecute={onExecute}
            onClose={() => setSelected(null)}
          />
        ) : null}
      </div>
      {!showAi ? (
        <Drawer pod={selected} detail={detail} insetClass="right-0" onClose={() => setSelected(null)} />
      ) : null}
    </div>
  );
}
