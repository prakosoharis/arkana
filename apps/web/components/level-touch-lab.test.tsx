import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { edgeLabel, edgeTone, judge, LevelTouchLab, resolvedShare, timeoutLabel, topRespected } from "./level-touch-lab";

const row = (over: Partial<Parameters<typeof judge>[0]> = {}) => ({
  event: "BOUNCE_FROM_ABOVE", distance: "FIXED_5", timeout_bars: 24,
  events: 8366, target_first: 3389, stop_first: 3693, unresolved: 1284, beyond_data: 0,
  target_rate: 0.405, target_rate_of_resolved: 0.479,
  regime: "SEMUA", break_even_rate: 0.5, edge: -0.021,
  ...over,
} as Parameters<typeof judge>[0]);

describe("judge", () => {
  it("refuses to grade a row with too few finished cases", () => {
    const state = judge(row({ target_first: 40, stop_first: 30 }), 300);
    expect(state.label).toBe("SAMPEL KURANG");
  });

  it("calls a below-even row exactly that", () => {
    // The real measurement: an EMA touch resolves in the trader's favour 47.9%
    // of the time, because the stop wins an ambiguous bar and the spread is paid.
    expect(judge(row(), 300).label).toBe("TIDAK UNGGUL");
  });

  it("separates barely-above-even from genuinely interesting", () => {
    // ARK-S31-02: the win rate alone no longer decides. Raising it without
    // moving the edge changes nothing, which is the whole point -- so these
    // fixtures set the edge, and a win rate on its own would not.
    expect(judge(row({ target_rate_of_resolved: 0.52, edge: 0.01 } as never), 300).label).toBe("TIPIS");
    expect(judge(row({ target_rate_of_resolved: 0.57, edge: 0.07 } as never), 300).label).toBe("MENARIK");
  });

  it("ignores a raised win rate that did not move the edge", () => {
    expect(judge(row({ target_rate_of_resolved: 0.72 } as never), 300).label).toBe("TIDAK UNGGUL");
  });
});

describe("resolvedShare", () => {
  it("says what fraction of touches finished at all", () => {
    // 40% of touches never reach either barrier in time, and a winrate quoted
    // without that number would look like a plan it is not.
    expect(resolvedShare(row())).toBeCloseTo(0.847, 3);
    expect(resolvedShare(row({ events: 0 }))).toBeNull();
  });
});

describe("LevelTouchLab", () => {
  it("states the pessimistic rules on the form, not in a footnote", () => {
    const markup = renderToStaticMarkup(<LevelTouchLab />);
    expect(markup).toContain("Uji Sentuhan Garis");
    expect(markup).toContain("PENGUKURAN SAJA");
    expect(markup).toContain("SL yang menang");
    // The default reaches the latest synced bar, so the disclosure shown first
    // is the one that belongs to that choice.
    expect(markup).toContain("Seluruh data dipakai");
    // ARK-S31-02 replaced this copy: the win rate stopped being the headline
    // once the break-even it has to beat moved with the geometry.
    expect(markup).toContain("Impas untuk bentuk sekarang");
  });

  it("does not offer to deploy, validate or confirm anything", () => {
    const markup = renderToStaticMarkup(<LevelTouchLab />);
    for (const forbidden of ["Deploy", "Confirm", "VALIDATED"]) {
      expect(markup).not.toContain(forbidden);
    }
  });
});

describe("timeoutLabel", () => {
  it("never prints the sentinel as a limit of zero", () => {
    expect(timeoutLabel(0)).toBe("tanpa batas");
    expect(timeoutLabel(24)).toBe("24");
  });
});

describe("LevelTouchLab time limit", () => {
  it("leaves the limit blank and says so on the field", () => {
    const markup = renderToStaticMarkup(<LevelTouchLab />);
    expect(markup).toContain("Batas waktu (opsional)");
    expect(markup).toContain("kosongkan = tanpa batas");
    expect(markup).toContain("Kosongkan saja");
  });
});

describe("LevelTouchLab coverage (ARK-S29-02)", () => {
  it("offers both spans and puts the price of each on the button", () => {
    const markup = renderToStaticMarkup(<LevelTouchLab />);
    expect(markup).toContain("Sampai data terkini");
    expect(markup).toContain("Sisakan 20% untuk vonis");
    expect(markup).toContain("ikut sync terbaru");
  });

  it("says out loud what using every bar costs", () => {
    // Pretending the reserve survives a hundred exploration runs would be the
    // larger dishonesty, so the trade is stated rather than withheld.
    const markup = renderToStaticMarkup(<LevelTouchLab />);
    expect(markup).toContain("Seluruh data dipakai");
    expect(markup).toContain("juri netral");
    expect(markup).toContain("forward test");
  });
});

describe("topRespected (ARK-S30-03)", () => {
  const line = (kind: string, period: number, rate: number, touches: number) => ({
    kind, period,
    respect: {
      SEMUA: { BUY: { touches, bounced: Math.round(touches * rate), broke: touches - Math.round(touches * rate), respect_rate: rate },
               SELL: { touches, bounced: 0, broke: touches, respect_rate: 1 - rate } },
      NAIK: { BUY: { touches, bounced: 0, broke: 0, respect_rate: rate + 0.05 },
              SELL: { touches, bounced: 0, broke: 0, respect_rate: rate } },
    },
  });

  it("ranks by the regime being shown, not by the whole history", () => {
    const rows = [line("EMA", 28, 0.507, 24000), line("SMA", 43, 0.509, 16000)] as never[];
    expect(topRespected(rows, "BUY", "SEMUA", 500).map(r => r.period)).toEqual([43, 28]);
    // Under NAIK both gain the same amount, so the order is unchanged --
    // the point is that it read the NAIK numbers at all.
    expect(topRespected(rows, "BUY", "NAIK", 500)[0].respect.NAIK.BUY.respect_rate).toBeCloseTo(0.559, 3);
  });

  it("drops a line with too few touches rather than letting it top the table", () => {
    const rows = [line("EMA", 28, 0.51, 24000), line("EMA", 199, 0.99, 12)] as never[];
    expect(topRespected(rows, "BUY", "SEMUA", 500).map(r => r.period)).toEqual([28]);
  });

  it("returns nothing at all when the regime was never measured", () => {
    const rows = [line("EMA", 28, 0.51, 24000)] as never[];
    expect(topRespected(rows, "BUY", "TURUN", 500)).toEqual([]);
  });

  it("takes only the requested number", () => {
    const rows = Array.from({ length: 12 }, (_, index) => line("EMA", 20 + index, 0.5 + index / 1000, 5000)) as never[];
    expect(topRespected(rows, "BUY", "SEMUA", 500)).toHaveLength(5);
    expect(topRespected(rows, "BUY", "SEMUA", 500, 3)).toHaveLength(3);
  });
});

describe("LevelTouchLab respect and scan", () => {
  it("offers the scan and says what it does not measure", () => {
    const markup = renderToStaticMarkup(<LevelTouchLab />);
    expect(markup).toContain("garis mana yang paling di-respect");
    expect(markup).toContain("bukan untung rugi");
    expect(markup).toContain("BELUM DIPINDAI");
  });

  it("exposes the trend controls that define the regimes", () => {
    const markup = renderToStaticMarkup(<LevelTouchLab />);
    expect(markup).toContain("Trend dinilai dari berapa candle");
    expect(markup).toContain("Ambang trend");
  });
});

describe("edge over break-even (ARK-S31-02)", () => {
  it("labels the edge with its sign, and nothing when it is unmeasured", () => {
    expect(edgeLabel(0.023)).toBe("+2.3");
    expect(edgeLabel(-0.031)).toBe("-3.1");
    expect(edgeLabel(null)).toBe("—");
  });

  it("colours a losing edge as losing however high the win rate is", () => {
    expect(edgeTone(0.02)).toBe("edge-good");
    expect(edgeTone(0.005)).toBe("edge-thin");
    expect(edgeTone(-0.01)).toBe("edge-bad");
  });

  it("judges a 66% win rate against a 66.7% break-even as a loss", () => {
    // The exact trap: shrinking the target buys a win rate the Owner asked for
    // and loses money. Ranking on the win rate would put this row first.
    const state = judge(row({ target_rate_of_resolved: 0.66, break_even_rate: 2 / 3, edge: -0.0067,
                              target_first: 6600, stop_first: 3400 } as never), 300);
    expect(state.label).toBe("TIDAK UNGGUL");
    expect(state.why).toContain("66.7%");
  });

  it("only calls a row interesting when it clears break-even by a real margin", () => {
    expect(judge(row({ edge: 0.025, break_even_rate: 0.5 } as never), 300).label).toBe("MENARIK");
    expect(judge(row({ edge: 0.004, break_even_rate: 0.5 } as never), 300).label).toBe("TIPIS");
    expect(judge(row({ edge: 0.02 } as never), 300).tone).toBe("strong");
  });
});

describe("LevelTouchLab geometry controls", () => {
  it("offers percent distances and says why they exist", () => {
    const markup = renderToStaticMarkup(<LevelTouchLab />);
    expect(markup).toContain("Persen dari harga");
    expect(markup).toContain("0,11% saat emas 4.500");
    expect(markup).toContain("TP = SL x berapa");
  });

  it("states the break-even the current geometry implies", () => {
    const markup = renderToStaticMarkup(<LevelTouchLab />);
    expect(markup).toContain("Impas untuk bentuk sekarang");
    expect(markup).toContain("50.0%");
  });
});
