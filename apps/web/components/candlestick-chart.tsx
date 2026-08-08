"use client";

import { useEffect, useRef } from "react";
import { ColorType, createChart } from "lightweight-charts";
import type { Bar } from "../lib/market";

export function CandlestickChart({ bars }: { bars: Bar[] }) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current || bars.length === 0) return;
    const chart = createChart(container.current, {
      width: container.current.clientWidth,
      height: 420,
      layout: { background: { type: ColorType.Solid, color: "#0b1620" }, textColor: "#b9c9d6" },
      grid: { vertLines: { color: "#1a2a37" }, horzLines: { color: "#1a2a37" } },
      timeScale: { borderColor: "#294150", timeVisible: true },
      rightPriceScale: { borderColor: "#294150" },
    });
    const series = chart.addCandlestickSeries({ upColor: "#41d48d", downColor: "#ff7280", borderVisible: false, wickUpColor: "#41d48d", wickDownColor: "#ff7280" });
    series.setData(bars.map((bar) => ({
      time: Math.floor(new Date(`${bar.timestamp}Z`).getTime() / 1000) as never,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    })));
    chart.timeScale().fitContent();
    const resize = new ResizeObserver(([entry]) => chart.applyOptions({ width: entry.contentRect.width }));
    resize.observe(container.current);
    return () => { resize.disconnect(); chart.remove(); };
  }, [bars]);

  return <div aria-label="Historical candlestick chart" className="chart" ref={container} />;
}
