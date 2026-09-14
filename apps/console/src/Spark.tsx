import { Area, AreaChart, ResponsiveContainer } from "recharts";

export function Spark({ values, color }: { values: number[]; color: string }) {
  if (!values.length) {
    return <div className="h-9 w-full rounded bg-navy/80" />;
  }
  const data = values.map((value, index) => ({ index, value }));
  return (
    <div className="h-9 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
          <Area type="monotone" dataKey="value" stroke={color} fill={color} fillOpacity={0.18} strokeWidth={1.6} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
