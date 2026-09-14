import { useMemo, useState } from "react";
import type { Workload } from "./types";
import { relativeTime, statusTone } from "./format";

export function Workloads({
  items,
  onSelect,
}: {
  items: Workload[];
  onSelect: (pod: Workload) => void;
}) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const filtered = useMemo(
    () =>
      items.filter((item) => {
        const hay = `${item.name} ${item.namespace} ${item.app || ""}`.toLowerCase();
        const matchQuery = hay.includes(query.toLowerCase());
        const matchStatus = status === "all" || item.status === status;
        return matchQuery && matchStatus;
      }),
    [items, query, status],
  );
  return (
    <div className="flex min-h-0 flex-1 flex-col rounded-lg border border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
        <h2 className="text-[11px] uppercase tracking-[0.16em] text-mute">Workloads</h2>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="filtrar"
          className="ml-auto w-32 rounded border border-line bg-navy px-2 py-1 text-[11px] outline-none focus:border-cyan/50"
        />
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className="rounded border border-line bg-navy px-2 py-1 text-[11px]"
        >
          <option value="all">todos</option>
          <option>Running</option>
          <option>Pending</option>
          <option>CrashLoopBackOff</option>
          <option>OOMKilled</option>
        </select>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full text-left text-[11px]">
          <thead className="sticky top-0 bg-panel text-[10px] uppercase tracking-[0.12em] text-mute">
            <tr>
              <th className="px-3 py-2 font-medium">Nome</th>
              <th className="px-2 py-2 font-medium">Ns</th>
              <th className="px-2 py-2 font-medium">Node</th>
              <th className="px-2 py-2 font-medium">Status</th>
              <th className="px-2 py-2 font-medium">R</th>
              <th className="px-2 py-2 font-medium">Imagem</th>
              <th className="px-3 py-2 font-medium">Idade</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((item) => (
              <tr
                key={`${item.namespace}/${item.name}`}
                onClick={() => onSelect(item)}
                className="cursor-pointer border-t border-line/60 hover:bg-raised/80"
              >
                <td className="px-3 py-1.5 font-mono">{item.app || item.name}</td>
                <td className="px-2 py-1.5 text-mute">{item.namespace}</td>
                <td className="max-w-[90px] truncate px-2 py-1.5 text-mute">{item.node || "—"}</td>
                <td className={`px-2 py-1.5 ${statusTone(item.status)}`}>{item.status}</td>
                <td className="px-2 py-1.5">{item.restarts}</td>
                <td className="max-w-[140px] truncate px-2 py-1.5 font-mono text-mute">
                  {(item.image || "").split("/").pop()}
                </td>
                <td className="px-3 py-1.5 text-mute">{relativeTime(item.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
