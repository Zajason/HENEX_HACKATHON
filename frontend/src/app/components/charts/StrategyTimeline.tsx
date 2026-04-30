import { useState } from 'react';
import type { DispatchWindow } from '../../data/AppDataContext';

function hourFromTime(time: string) {
  const parsed = Number(time.split(':')[0]);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function StrategyTimeline({ windows }: { windows: DispatchWindow[] }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  return (
    <div className="relative">
      {/* Timeline */}
      <div className="mb-4 flex items-center gap-1 overflow-x-auto pb-1">
        {Array.from({ length: 24 }).map((_, i) => (
          <div key={i} className="relative min-w-10 flex-1">
            <div className="flex h-14 items-center justify-center rounded border border-slate-700/40 bg-white/[0.018] text-xs text-slate-500">
              {i.toString().padStart(2, '0')}
            </div>
          </div>
        ))}
      </div>

      {/* Strategy Bars */}
      <div className="relative h-24 mb-6">
        {windows.map((strategy, index) => {
          const startHour = hourFromTime(strategy.start);
          const endHour = hourFromTime(strategy.end);
          const left = (startHour / 24) * 100;
          const width = (Math.max(endHour - startHour, 1) / 24) * 100;

          return (
            <div
              key={strategy.id}
              className="absolute h-16 cursor-pointer rounded-md transition-all duration-200"
              style={{
                left: `${left}%`,
                width: `${width}%`,
                background: strategy.type === 'charge'
                  ? 'linear-gradient(90deg, rgba(56, 189, 248, 0.16) 0%, rgba(56, 189, 248, 0.32) 100%)'
                  : 'linear-gradient(90deg, rgba(110, 231, 183, 0.16) 0%, rgba(110, 231, 183, 0.32) 100%)',
                border: `1px solid ${strategy.type === 'charge' ? 'rgba(56, 189, 248, 0.45)' : 'rgba(110, 231, 183, 0.45)'}`,
                transform: hoveredIndex === index ? 'translateY(-2px)' : 'translateY(0)',
                boxShadow: hoveredIndex === index
                  ? `0 14px 30px ${strategy.type === 'charge' ? 'rgba(56, 189, 248, 0.12)' : 'rgba(110, 231, 183, 0.12)'}`
                  : 'none'
              }}
              onMouseEnter={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
            >
              <div className="flex flex-col items-center justify-center h-full px-4">
                <div className="mb-1 font-medium text-white">
                  {strategy.type === 'charge' ? 'Charge' : 'Discharge'}
                </div>
                <div className="text-xs text-slate-300">
                  €{strategy.profit} margin
                </div>
              </div>

              {/* Tooltip */}
              {hoveredIndex === index && (
                <div className="absolute left-1/2 top-full z-10 mt-2 -translate-x-1/2 whitespace-nowrap rounded-md border border-slate-600/60 bg-[#0b1016] p-3 text-sm shadow-xl">
                  <div className="text-white mb-1">{strategy.start}-{strategy.end}</div>
                  <div className="text-emerald-200">Expected: €{strategy.profit}</div>
                  <div className="text-sky-300">Z-score: {strategy.zscore}</div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-6 text-sm">
        <div className="flex items-center gap-2">
          <div className="h-3 w-3 rounded-sm border border-sky-300 bg-sky-300/30"></div>
          <span className="text-slate-400">Charging below median</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="h-3 w-3 rounded-sm border border-emerald-300 bg-emerald-300/30"></div>
          <span className="text-slate-400">Selling peak spread</span>
        </div>
      </div>
    </div>
  );
}
