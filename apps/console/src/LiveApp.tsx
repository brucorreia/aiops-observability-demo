import { useEffect, useState } from "react";

type ApiBody = {
  status?: number;
  version?: string;
  checkout_reais?: number;
};

function formatReais(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function LiveApp({ reloadKey }: { reloadKey: number }) {
  const [health, setHealth] = useState<"up" | "down">("down");
  const [api, setApi] = useState<ApiBody | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const healthRes = await fetch("/live/demo/health");
        const apiRes = await fetch("/live/demo/api");
        const apiBody =
          apiRes.ok || apiRes.status === 500 ? ((await apiRes.json()) as ApiBody) : null;
        if (cancelled) return;
        setHealth(healthRes.ok ? "up" : "down");
        setApi(apiBody);
      } catch {
        if (!cancelled) {
          setHealth("down");
          setApi(null);
        }
      }
    }
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [reloadKey]);

  const amount = api?.checkout_reais;
  const down = health === "down";
  const title = down ? "Checkout indisponível" : "Checkout operacional";
  const tone = down ? "border-bad/50 bg-bad/10" : "border-ok/40 bg-ok/10";

  return (
    <section className={`relative flex min-h-0 flex-col overflow-hidden rounded-lg border ${tone}`}>
      <div className="flex items-center justify-between border-b border-line/70 px-4 py-2">
        <div>
          <div className="text-[11px] uppercase tracking-[0.16em] text-mute">demo-app</div>
          <div className="text-sm">{title}</div>
        </div>
        <div className="font-mono text-[11px] text-mute">{down ? "Fora do ar" : "Ready"}</div>
      </div>
      <div className="flex flex-1 items-center justify-center p-6">
        <div className="w-full max-w-sm rounded-lg border border-line bg-panel p-5">
          <div className="text-[11px] uppercase tracking-[0.16em] text-mute">Pedido #4821</div>
          <div className={`mt-2 text-2xl tabular-nums ${down ? "text-bad" : "text-ok"}`}>
            {down ? "—" : formatReais(amount)}
          </div>
          <div className="mt-1 text-[11px] text-mute">+ R$ 7,00 / s via /api</div>
          <div className="mt-4 h-2 rounded bg-navy">
            <div className={`h-2 rounded ${down ? "w-1/5 bg-bad" : "w-4/5 bg-ok"}`} />
          </div>
          <p className="mt-4 text-[12px] leading-5 text-mute">
            {down
              ? "/health não responde. O pod não fica Ready — a causa entra na análise da IA depois do alerta."
              : "/health e /api responderam 200. O valor do checkout sobe a cada segundo."}
          </p>
        </div>
      </div>
    </section>
  );
}
