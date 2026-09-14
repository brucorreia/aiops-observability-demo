import type { Workload } from "./types";
import { statusTone } from "./format";

function PodChip({ pod, onSelect }: { pod: Workload; onSelect: (pod: Workload) => void }) {
  const bad = pod.status === "CrashLoopBackOff" || pod.status === "OOMKilled";
  const warn = pod.status === "Pending" || !pod.ready;
  return (
    <button
      type="button"
      onClick={() => onSelect(pod)}
      className={`w-full rounded border px-2 py-1.5 text-left transition hover:border-cyan/50 ${
        bad
          ? "pulse-bad border-bad/70 bg-bad/10"
          : warn
            ? "border-warn/40 bg-warn/10"
            : "border-ok/30 bg-ok/5"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-mono text-[11px]">{pod.app || pod.name}</span>
        <span className={`text-[10px] uppercase tracking-[0.12em] ${statusTone(pod.status)}`}>
          {pod.status}
        </span>
      </div>
      <div className="mt-0.5 truncate text-[10px] text-mute">{pod.namespace}</div>
    </button>
  );
}

export function Topology({
  nodes,
  unscheduled,
  onSelect,
}: {
  nodes: Array<{ name: string; ready: boolean; pods: Workload[] }>;
  unscheduled: Workload[];
  onSelect: (pod: Workload) => void;
}) {
  const columns = Math.max(nodes.length, 1);
  return (
    <div className="rounded-lg border border-line bg-panel p-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-[11px] uppercase tracking-[0.16em] text-mute">Topologia</h2>
        <span className="text-[10px] text-mute">cluster k3d-aiops</span>
      </div>
      <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
        {nodes.map((node) => (
          <div key={node.name} className="rounded-md border border-line/80 bg-navy/70 p-2">
            <div className="mb-2 flex items-center justify-between">
              <span className="truncate font-mono text-[11px] text-cyan">{node.name}</span>
              <span className={node.ready ? "text-ok" : "text-bad"}>●</span>
            </div>
            <div className="space-y-1.5">
              {node.pods.map((pod) => (
                <PodChip key={pod.name} pod={pod} onSelect={onSelect} />
              ))}
              {!node.pods.length && <div className="text-[11px] text-mute">sem workloads da demo</div>}
            </div>
          </div>
        ))}
      </div>
      {unscheduled.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {unscheduled.map((pod) => (
            <PodChip key={pod.name} pod={pod} onSelect={onSelect} />
          ))}
        </div>
      )}
    </div>
  );
}
