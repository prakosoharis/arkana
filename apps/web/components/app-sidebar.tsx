import Link from "next/link";

/**
 * ARK-S26-00. Fifteen entries were listed as one flat menu, ordered by the
 * sprint that built them rather than by what the Owner is trying to do. Six of
 * them serve governance and internal research and were read as unfinished
 * features. Nothing is removed -- the ordering states which are on the path
 * from market data to a trade decision, and which are not.
 */
const MAIN: Array<[string, string, string]> = [
  ["/", "Data Pasar", "Impor dan sinkronisasi data MetaTrader"],
  ["/explore", "Eksplorasi Market", "Jam berapa sering merah, pola naik-turun, tanpa strategi"],
  ["/level-touch", "Uji Sentuhan Garis", "Harga menyentuh EMA: duluan TP atau SL?"],
  ["/strategies", "Strategi", "Susun dan simpan kontrak strategi"],
  ["/backtest", "Backtest", "Uji strategi ke data historis"],
  ["/capital", "Simulasi Modal", "Berapa hasilnya kalau dipakai dengan modal segini"],
  ["/current-decision", "Keputusan Sekarang", "Long / short / no-trade beserta SL dan TP"],
];

const ADVANCED: Array<[string, string]> = [
  ["/command-center", "Command Center · pantau EA di MT5"],
  ["/discovery", "Eksplorasi Pola · 4 pola bawaan, digantikan Eksplorasi Market"],
  ["/research", "Research Lab · rumuskan pertanyaan riset"],
  ["/variants", "Variant Explorer · bandingkan variasi parameter"],
  ["/edge-search", "Edge Search · kampanye pencarian massal"],
  ["/deployments", "Legacy Demo Deployment"],
  ["/demo-forward", "Generic DEMO Forward"],
  ["/governance", "Governance & Readiness · jejak audit"],
];

export function AppSidebar() {
  return <aside className="sidebar">
    <div className="brand"><span>△</span><div><strong>ARKANA</strong><small>TRADING INTELLIGENCE</small></div></div>
    <p className="section-label">ALUR UTAMA</p>
    {MAIN.map(([href, label, hint]) => <Link className="nav" href={href} key={href}>{label}<small>{hint}</small></Link>)}
    <details className="nav-advanced">
      <summary>Lanjutan &amp; tata kelola</summary>
      {ADVANCED.map(([href, label]) => <Link className="nav" href={href} key={href}>{label}</Link>)}
      <button className="nav disabled" disabled>Positions · belum dibuat</button>
      <button className="nav disabled" disabled>Settings · belum dibuat</button>
    </details>
    <div className="safety"><strong>DEMO OBSERVABILITY</strong><small>Research and telemetry only. LIVE remains locked.</small></div>
  </aside>;
}
