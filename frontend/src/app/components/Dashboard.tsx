import { Calendar } from "lucide-react";
import { PriceChart } from "./charts/PriceChart";
import { SoCChart } from "./charts/SoCChart";
import { StrategyTimeline } from "./charts/StrategyTimeline";
import { PerformanceMetrics } from "./PerformanceMetrics";
import { DecisionLog } from "./DecisionLog";

function Panel({
  title,
  children,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-2xl border border-white/10 bg-[#141920]/60 p-6 backdrop-blur-xl ${className}`}
    >
      <h3 className="mb-4 text-white">{title}</h3>
      {children}
    </div>
  );
}

export function Dashboard() {
  return (
    <div className="p-4 md:p-8">
      <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="mb-2 text-3xl font-semibold text-white">
            Battery Optimization Engine
          </h1>
          <p className="text-gray-400">AI-powered energy trading system</p>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-[#141920] px-4 py-2">
            <Calendar className="h-4 w-4 text-gray-400" />
            <span className="text-white">Day-Ahead</span>
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-green-500/30 bg-green-500/10 px-4 py-2">
            <div className="h-2 w-2 rounded-full bg-green-400" />
            <span className="text-green-400">Forecast Ready</span>
          </div>
        </div>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Panel title="Day-Ahead Price Curve">
          <PriceChart />
        </Panel>

        <Panel title="Battery State of Charge">
          <SoCChart />
        </Panel>
      </div>

      <Panel title="Optimal Strategy" className="mb-6">
        <StrategyTimeline />
      </Panel>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Panel title="Performance">
          <PerformanceMetrics />
        </Panel>

        <Panel title="Decision Log">
          <DecisionLog />
        </Panel>
      </div>
    </div>
  );
}
