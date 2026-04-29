import { Calendar } from "lucide-react";
import { PriceChart } from "./charts/PriceChart";
import { SoCChart } from "./charts/SoCChart";
import { StrategyTimeline } from "./charts/StrategyTimeline";
import { PerformanceMetrics } from "./PerformanceMetrics";
import { DecisionLog } from "./DecisionLog";

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
      className={`surface rounded-lg p-5 md:p-6 ${className}`}
    >
      {eyebrow && <div className="eyebrow mb-2">{eyebrow}</div>}
      <h3 className="mb-4 text-base font-semibold text-white">{title}</h3>
      {children}
    </div>
  );
}

export function Dashboard() {
  return (
    <div className="p-4 md:p-8">
      <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="eyebrow mb-3">Intraday operating view</div>
          <h1 className="mb-2 text-3xl font-semibold leading-tight text-white">
            HENEX battery dispatch
          </h1>
          <p className="max-w-2xl text-slate-400">
            Price spreads, state of charge, and the next executable trading windows in one place.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2 rounded-lg border border-slate-700/60 bg-white/[0.03] px-4 py-2">
            <Calendar className="h-4 w-4 text-slate-400" />
            <span className="text-white">Day-Ahead</span>
          </div>

          <div className="flex items-center gap-2 rounded-lg border border-emerald-300/30 bg-emerald-300/10 px-4 py-2">
            <div className="h-2 w-2 rounded-full bg-emerald-300" />
            <span className="text-emerald-200">Forecast locked</span>
          </div>
        </div>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Panel title="Day-ahead price curve" eyebrow="EPEX EUR/MWh">
          <PriceChart />
        </Panel>

        <Panel title="State of charge forecast" eyebrow="40 MWh fleet">
          <SoCChart />
        </Panel>
      </div>

      <Panel title="Dispatch windows" eyebrow="Recommended schedule" className="mb-6">
        <StrategyTimeline />
      </Panel>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Panel title="Desk performance" eyebrow="Today">
          <PerformanceMetrics />
        </Panel>

        <Panel title="Decision trail" eyebrow="Model rationale">
          <DecisionLog />
        </Panel>
      </div>
    </div>
  );
}
