import { Calendar } from "lucide-react";
import { PriceChart } from "./charts/PriceChart";
import { SoCChart } from "./charts/SoCChart";
import { StrategyTimeline } from "./charts/StrategyTimeline";
import { PerformanceMetrics } from "./PerformanceMetrics";
import { DecisionLog } from "./DecisionLog";
import { useAppData } from "../data/AppDataContext";

function Panel({
  title,
  eyebrow,
  children,
  className = "",
}: {
  title: string;
  eyebrow?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`surface rounded-md p-5 md:p-6 ${className}`}
    >
      {eyebrow && <div className="eyebrow mb-2">{eyebrow}</div>}
      <h3 className="mb-4 text-base font-semibold text-white">{title}</h3>
      {children}
    </div>
  );
}

export function Dashboard() {
  const {
    priceData,
    socData,
    dispatchWindows,
    tradingSummary,
  } = useAppData();
  const primaryWindow = dispatchWindows.find((window) => window.type === 'discharge') ?? dispatchWindows[0];

  return (
    <div className="mx-auto max-w-7xl p-4 md:p-8">
      <div className="mb-6 grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div>
          <div className="mb-3 text-sm text-slate-500">Live desk / Day-ahead nomination</div>
          <h1 className="max-w-3xl text-4xl font-semibold leading-tight text-white">HENEX battery dispatch</h1>
          <p className="max-w-2xl text-slate-400">
            Price spreads, state of charge, and the next executable trading windows in one place.
          </p>

          <div className="mt-6 flex flex-wrap gap-3">
            <div className="flex items-center gap-2 rounded-md border border-slate-700/60 bg-black/10 px-3 py-2 text-sm">
              <Calendar className="h-4 w-4 text-slate-500" />
              <span className="text-slate-200">Day-ahead</span>
            </div>
            <div className="flex items-center gap-2 rounded-md border border-[#9ed9c5]/35 bg-[#9ed9c5]/10 px-3 py-2 text-sm">
              <div className="h-1.5 w-1.5 rounded-full bg-[#9ed9c5]" />
              <span className="text-[#d9fff2]">Forecast ready</span>
            </div>
          </div>
        </div>

        <aside className="surface-muted rounded-md p-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="text-sm font-semibold text-white">Next nomination</div>
            <span className="rounded border border-[#9ed9c5]/30 px-2 py-1 text-xs text-[#bcebdc]">Draft</span>
          </div>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between gap-4">
              <span className="text-slate-500">Charge</span>
              <span className="text-white">
                {dispatchWindows.find((window) => window.type === 'charge')?.start ?? '--'}-
                {dispatchWindows.find((window) => window.type === 'charge')?.end ?? '--'}
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-slate-500">Sell</span>
              <span className="text-white">
                {primaryWindow?.start ?? '--'}-{primaryWindow?.end ?? '--'}
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-slate-500">Expected margin</span>
              <span className="text-[#d9fff2]">€{(primaryWindow?.profit ?? 0).toLocaleString()}</span>
            </div>
          </div>
          <div className="mt-4 border-t border-slate-700/50 pt-3 text-xs leading-relaxed text-slate-500">
            Waiting on final price publication before this slot moves from draft to scheduled.
          </div>
        </aside>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.75fr)]">
        <Panel title="Day-ahead price curve" eyebrow="EPEX EUR/MWh">
          <PriceChart data={priceData} />
        </Panel>

        <Panel title="State of charge forecast" eyebrow="40 MWh fleet">
          <SoCChart data={socData} />
        </Panel>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Panel title="Dispatch windows" eyebrow="Dispatch draft">
          <StrategyTimeline windows={dispatchWindows} />
        </Panel>

        <Panel title="Decision trail" eyebrow="Decision notes">
          <DecisionLog />
        </Panel>
      </div>

      <Panel title="Trading summary" eyebrow="Today">
        <PerformanceMetrics summary={tradingSummary} />
      </Panel>
    </div>
  );
}
