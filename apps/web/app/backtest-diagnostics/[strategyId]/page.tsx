import { BacktestDiagnostics } from "../../../components/backtest-diagnostics";

export default async function Page({ params }: { params: Promise<{ strategyId: string }> }) {
  return <BacktestDiagnostics strategyId={(await params).strategyId} />;
}
