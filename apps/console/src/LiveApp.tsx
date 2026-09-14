import { useEffect, useState } from "react";

type Order = {
  pedido?: number;
  valor?: number;
  checkout_reais?: number;
};

function formatReais(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function asOrder(body: Order | null): Order | null {
  if (!body) return null;
  const valor = body.valor ?? body.checkout_reais;
  if (valor == null) return null;
  return { pedido: body.pedido, valor };
}

export function LiveApp({
  reloadKey,
  fallbackOrder,
}: {
  reloadKey: number;
  fallbackOrder?: Order | null;
}) {
  const [health, setHealth] = useState<"up" | "down">("down");
  const [orders, setOrders] = useState<Order[]>([]);

  useEffect(() => {
    let cancelled = false;
    let active: AbortController | null = null;
    async function tick() {
      active?.abort();
      const controller = new AbortController();
      active = controller;
      try {
        const healthRes = await fetch("/live/demo/health", { signal: controller.signal });
        const apiRes = await fetch("/live/demo/api", { signal: controller.signal });
        let apiBody: Order | null = null;
        if (apiRes.ok || apiRes.status === 500) {
          apiBody = asOrder((await apiRes.json()) as Order);
        }
        if (cancelled || controller.signal.aborted) return;
        setHealth(healthRes.ok ? "up" : "down");
        if (apiBody?.pedido != null) {
          setOrders((prev) => {
            if (prev[0]?.pedido === apiBody.pedido) return prev;
            return [apiBody, ...prev].slice(0, 7);
          });
        }
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === "AbortError")) return;
        setHealth("down");
      }
    }
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => {
      cancelled = true;
      active?.abort();
      window.clearInterval(timer);
    };
  }, [reloadKey]);

  const down = health === "down";
  const latest = orders[0] || asOrder(fallbackOrder || null);
  const title = down ? "Checkout indisponível" : "Checkout operacional";
  const tone = down ? "border-bad/50 bg-bad/10" : "border-ok/40 bg-ok/10";

  return (
    <section className={`relative flex min-h-0 flex-col overflow-hidden rounded-lg border ${tone}`}>
      <div className="flex items-center justify-between border-b border-line/70 px-4 py-2">
        <div>
          <div className="text-[11px] uppercase tracking-[0.16em] text-mute">Checkout</div>
          <div className="text-sm">{title}</div>
        </div>
        <div className="font-mono text-[11px] text-mute">{down ? "Fora do ar" : "Ready"}</div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-3 p-4">
        <div className="rounded-lg border border-line bg-panel p-4">
          <div className="text-[11px] uppercase tracking-[0.16em] text-mute">
            {latest?.pedido != null ? `Pedido #${latest.pedido}` : "Aguardando pedido"}
          </div>
          <div className={`mt-2 text-2xl tabular-nums ${down ? "text-bad" : "text-ok"}`}>
            {down ? "—" : formatReais(latest?.valor)}
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-line bg-navy/50">
          {(down ? [] : orders).map((item, index) => (
            <div
              key={`${item.pedido}-${index}`}
              className="flex items-center justify-between gap-3 border-b border-line/60 px-3 py-2 last:border-b-0"
            >
              <div className="font-mono text-[12px] text-mute">#{item.pedido}</div>
              <div className={`font-mono text-[12px] ${index === 0 ? "text-ok" : "text-white"}`}>
                {formatReais(item.valor)}
              </div>
            </div>
          ))}
          {down || !orders.length ? (
            <div className="px-3 py-4 text-[12px] text-mute">sem pedidos</div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
