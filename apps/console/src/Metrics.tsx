import type { ClusterStatus } from "./types";
import { formatBytes, formatCores, relativeTime } from "./format";
import { Spark } from "./Spark";

function Card({
  label,
  value,
  hint,
  spark,
  color,
}: {
  label: string;
  value: string;
  hint?: string;
  spark?: number[];
  color: string;
}) {
  return (
    <div className="rounded-lg border border-line bg-panel/90 p-3 shadow-panel">
      <div className="text-[10px] uppercase tracking-[0.16em] text-mute">{label}</div>
      <div className="mt-1 flex items-end justify-between gap-3">
        <div className="text-xl font-medium leading-none">{value}</div>
        {hint ? <div className="text-[11px] text-mute">{hint}</div> : null}
      </div>
      {spark ? <div className="mt-2"><Spark values={spark} color={color} /></div> : null}
    </div>
  );
}

export function Metrics({ status }: { status: ClusterStatus }) {
  const failingWorkload = status.workloads.some(
    (item) => item.status === "CrashLoopBackOff" || item.status === "OOMKilled",
  );
  const httpFailing = status.demo_app.api?.status === 500;
  const activeIncidents = failingWorkload || httpFailing ? 1 : 0;
  return (
    <section className="grid grid-cols-4 gap-3 px-6 py-3">
      <Card
        label="Cluster health"
        value={status.health}
        hint={`${status.demo_app.ready}/${status.demo_app.total} demo-app Ready`}
        color={status.health === "Healthy" ? "#3ddc97" : "#ff6b6b"}
      />
      <Card
        label="Nodes"
        value={`${status.nodes.ready}/${status.nodes.total} Ready`}
        color="#4f8cff"
      />
      <Card
        label="Pods"
        value={`${status.pods.running}/${status.pods.total}`}
        hint="aiops-demo + ai-agent"
        color="#3ee0f0"
      />
      <Card
        label="CPU"
        value={formatCores(status.cpu.cores)}
        spark={status.cpu.sparkline}
        color="#4f8cff"
      />
      <Card
        label="Memória"
        value={formatBytes(status.memory.bytes)}
        spark={status.memory.sparkline}
        color="#8b7cff"
      />
      <Card label="Restarts" value={String(Math.round(status.restarts || 0))} color="#f5c542" />
      <Card
        label="Incidentes"
        value={String(activeIncidents)}
        hint={status.rollout?.mode || "nenhum disparado"}
        color="#ff6b6b"
      />
      <Card
        label="Último deploy"
        value={relativeTime(status.demo_app.deployed_at)}
        hint={status.demo_app.git_sha || "—"}
        color="#3ee0f0"
      />
    </section>
  );
}
