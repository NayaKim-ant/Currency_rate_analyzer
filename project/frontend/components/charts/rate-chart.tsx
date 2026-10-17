"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export type ChartPoint = {
  date: string;
  rate: number;
  ma_5: number | null;
  ma_20: number | null;
  ma_60: number | null;
};

type RateChartProps = {
  points: ChartPoint[];
  currency: string;
};

function formatTick(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: Math.abs(value) < 10 ? 4 : 2 }).format(value);
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

export function RateChart({ points, currency }: RateChartProps) {
  return (
    <div className="chart-canvas" role="img" aria-label={`Korean won cost of 1 ${currency} with 5, 20 and 60 observation moving averages. Lower values cost fewer won.`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 14, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="rateFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#137a62" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#137a62" stopOpacity={0.015} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="#e6ebe7" strokeDasharray="2 4" />
          <XAxis dataKey="date" tickFormatter={formatDate} minTickGap={34} axisLine={false} tickLine={false} tick={{ fill: "#7c8982", fontSize: 11 }} />
          <YAxis orientation="right" width={80} tickFormatter={(value) => `₩${formatTick(Number(value))}`} axisLine={false} tickLine={false} tick={{ fill: "#7c8982", fontSize: 11 }} domain={["auto", "auto"]} />
          <Tooltip
            labelFormatter={(label) => formatDate(String(label))}
            formatter={(value, name) => [value == null ? "--" : `₩${formatTick(Number(value))} / 1 ${currency}`, String(name).replaceAll("_", " ").toUpperCase()]}
            contentStyle={{ border: "1px solid #dfe6e1", borderRadius: 4, boxShadow: "0 8px 24px #18241c12", fontSize: 12 }}
          />
          <Area type="monotone" dataKey="rate" name="Rate" stroke="#137a62" strokeWidth={2.2} fill="url(#rateFill)" dot={false} activeDot={{ r: 4, fill: "#137a62", stroke: "#fff", strokeWidth: 2 }} />
          <Area type="monotone" dataKey="ma_5" name="MA 5" stroke="#dc7548" strokeWidth={1.5} fill="none" dot={false} connectNulls />
          <Area type="monotone" dataKey="ma_20" name="MA 20" stroke="#4469a3" strokeWidth={1.5} fill="none" dot={false} connectNulls />
          <Area type="monotone" dataKey="ma_60" name="MA 60" stroke="#84954e" strokeWidth={1.5} fill="none" dot={false} connectNulls />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
