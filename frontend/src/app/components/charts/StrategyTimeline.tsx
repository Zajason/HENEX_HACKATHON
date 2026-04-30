import { useState } from 'react';
import type { DispatchWindow } from '../../data/AppDataContext';

const minutesPerDay = 24 * 60;
const slotMinutes = 15;
const slotsPerDay = minutesPerDay / slotMinutes;
const labeledSlotInterval = 8;

function minutesFromTime(time: string) {
  const [hour = '0', minute = '0'] = time.split(':');
  const parsedHour = Number(hour);
  const parsedMinute = Number(minute);
  if (!Number.isFinite(parsedHour) || !Number.isFinite(parsedMinute)) return 0;
  return Math.min(Math.max(parsedHour * 60 + parsedMinute, 0), minutesPerDay);
}

function formatSlot(index: number) {
  const totalMinutes = index * slotMinutes;
  const hour = Math.floor(totalMinutes / 60);
  const minute = totalMinutes % 60;
  return `${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;
}

export function StrategyTimeline({ windows }: { windows: DispatchWindow[] }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  return (
    <div className="relative">
      <div className="mb-6 overflow-x-auto pb-1">
        <div className="min-w-[960px]">
          {/* Timeline */}
          <div className="mb-4 grid grid-cols-[repeat(96,minmax(10px,1fr))] gap-px">
            {Array.from({ length: slotsPerDay }).map((_, i) => (
              <div key={i} className="relative">
                <div
                  className={`flex h-14 items-center justify-center rounded-sm border text-[10px] ${
                    i % 4 === 0
                      ? 'border-slate-600/50 bg-white/[0.03] text-slate-400'
                      : 'border-slate-800/50 bg-white/[0.012] text-slate-600'
                  }`}
                  title={formatSlot(i)}
                >
                  {i % labeledSlotInterval === 0 ? formatSlot(i) : ''}
                </div>
              </div>
            ))}
          </div>

          {/* Strategy Bars */}
          <div className="relative h-24">
            {windows.map((strategy, index) => {
              const startMinutes = minutesFromTime(strategy.start);
              const endMinutes = minutesFromTime(strategy.end);
              const left = (startMinutes / minutesPerDay) * 100;
              const width = (Math.max(endMinutes - startMinutes, slotMinutes) / minutesPerDay) * 100;

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
                  <div className="flex h-full flex-col items-center justify-center px-4">
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
                      <div className="mb-1 text-white">{strategy.start}-{strategy.end}</div>
                      <div className="text-emerald-200">Expected: €{strategy.profit}</div>
                      <div className="text-sky-300">Z-score: {strategy.zscore}</div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
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
