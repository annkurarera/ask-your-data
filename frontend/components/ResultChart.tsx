"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AskResponse } from "@/lib/types";
import {
  compactINR,
  formatCell,
  formatNumber,
  humanizeColumn,
  isCroreColumn,
  isLakhColumn,
  isMoneyColumn,
  isPctColumn,
} from "@/lib/format";

const SERIES = ["var(--cheque)", "var(--teal)", "var(--amber)"];

export default function ResultChart({ data }: { data: AskResponse }) {
  const { chart, columns, rows } = data;

  if (chart.type === "kpi" && chart.y) {
    return (
      <div className="kpis" data-testid="kpi">
        {chart.y.map((col) => {
          const v = rows[0][columns.indexOf(col)];
          const money = isMoneyColumn(col);
          const big = typeof v === "number" && money && Math.abs(v) >= 1e5;
          return (
            <div className="kpi" key={col}>
              <div className="kpi-value">{big ? compactINR(v as number, true) : formatCell(v, col)}</div>
              <div className="kpi-label">{humanizeColumn(col)}</div>
              {big && <div className="kpi-exact">{formatCell(v, col)}</div>}
            </div>
          );
        })}
      </div>
    );
  }

  if ((chart.type !== "bar" && chart.type !== "line") || !chart.x || !chart.y?.length) return null;

  const x = chart.x;
  const ys = chart.y;
  const points = rows.map((r) => {
    const o: Record<string, unknown> = { [x]: formatCell(r[columns.indexOf(x)], x) };
    ys.forEach((y) => (o[y] = r[columns.indexOf(y)]));
    return o;
  });
  const money = isMoneyColumn(ys[0]);
  const pct = isPctColumn(ys[0]);
  const tick = (v: number) =>
    pct
      ? `${v}%`
      : isCroreColumn(ys[0])
        ? `₹${formatNumber(v)} Cr`
        : isLakhColumn(ys[0])
          ? `₹${formatNumber(v)} L`
          : compactINR(v, money);
  const horizontal = chart.type === "bar" && rows.length > 6;
  const height = horizontal ? Math.max(220, rows.length * 30 + 40) : 260;
  const axisStyle = { fontSize: 12, fill: "var(--muted)" };
  const tooltip = (
    <Tooltip
      formatter={(v, name) => [formatCell(v, String(name)), humanizeColumn(String(name))]}
      contentStyle={{
        background: "var(--surface)",
        border: "1px solid var(--line)",
        borderRadius: 6,
        color: "var(--ink)",
        fontSize: 13,
      }}
      cursor={{ fill: "var(--hover)" }}
    />
  );

  return (
    <div className="chart" data-testid={`chart-${chart.type}`} aria-label={`${chart.type} chart of ${ys.join(", ")} by ${x}`}>
      <ResponsiveContainer width="100%" height={height}>
        {chart.type === "line" ? (
          <LineChart data={points} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey={x} tick={axisStyle} tickLine={false} axisLine={{ stroke: "var(--line)" }} minTickGap={16} />
            <YAxis tickFormatter={tick} tick={axisStyle} tickLine={false} axisLine={false} width={72} />
            {tooltip}
            {ys.map((y, i) => (
              <Line key={y} dataKey={y} stroke={SERIES[i]} strokeWidth={2} dot={rows.length <= 24} type="monotone" />
            ))}
          </LineChart>
        ) : horizontal ? (
          <BarChart data={points} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 8 }}>
            <CartesianGrid stroke="var(--line)" horizontal={false} />
            <XAxis type="number" tickFormatter={tick} tick={axisStyle} tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey={x} tick={axisStyle} tickLine={false} axisLine={false} width={130} />
            {tooltip}
            {ys.map((y, i) => (
              <Bar key={y} dataKey={y} fill={SERIES[i]} radius={[0, 3, 3, 0]} maxBarSize={18} />
            ))}
          </BarChart>
        ) : (
          <BarChart data={points} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey={x} tick={axisStyle} tickLine={false} axisLine={{ stroke: "var(--line)" }} interval={0} />
            <YAxis tickFormatter={tick} tick={axisStyle} tickLine={false} axisLine={false} width={72} />
            {tooltip}
            {ys.map((y, i) => (
              <Bar key={y} dataKey={y} fill={SERIES[i]} radius={[3, 3, 0, 0]} maxBarSize={48} />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
