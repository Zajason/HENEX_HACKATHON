import { useState } from 'react';

const strategies = [
  { time: '02:00-06:00', type: 'charge', profit: 245, zscore: 2.1 },
  { time: '09:00-13:00', type: 'discharge', profit: 890, zscore: 2.8 },
  { time: '15:00-19:00', type: 'discharge', profit: 1240, zscore: 3.2 },
];

export function StrategyTimeline() {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  return (
    <div className="relative">
      {/* Timeline */}
      <div className="flex items-center gap-1 mb-4">
        {Array.from({ length: 24 }).map((_, i) => (
          <div key={i} className="flex-1 relative">
            <div className="h-16 rounded border border-white/5 bg-white/[0.02] flex items-center justify-center text-xs text-gray-500">
              {i.toString().padStart(2, '0')}
            </div>
          </div>
        ))}
      </div>

      {/* Strategy Bars */}
      <div className="relative h-24 mb-6">
        {strategies.map((strategy, index) => {
          const [start, end] = strategy.time.split('-');
          const startHour = parseInt(start.split(':')[0]);
          const endHour = parseInt(end.split(':')[0]);
          const left = (startHour / 24) * 100;
          const width = ((endHour - startHour) / 24) * 100;

          return (
            <div
              key={index}
              className="absolute h-16 rounded-xl cursor-pointer transition-all duration-200"
              style={{
                left: `${left}%`,
                width: `${width}%`,
                background: strategy.type === 'charge'
                  ? 'linear-gradient(90deg, rgba(59, 130, 246, 0.3) 0%, rgba(59, 130, 246, 0.5) 100%)'
                  : 'linear-gradient(90deg, rgba(16, 185, 129, 0.3) 0%, rgba(16, 185, 129, 0.5) 100%)',
                border: `1px solid ${strategy.type === 'charge' ? 'rgba(59, 130, 246, 0.5)' : 'rgba(16, 185, 129, 0.5)'}`,
                transform: hoveredIndex === index ? 'scale(1.02)' : 'scale(1)',
                boxShadow: hoveredIndex === index
                  ? `0 0 20px ${strategy.type === 'charge' ? 'rgba(59, 130, 246, 0.4)' : 'rgba(16, 185, 129, 0.4)'}`
                  : 'none'
              }}
              onMouseEnter={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
            >
              <div className="flex flex-col items-center justify-center h-full px-4">
                <div className="text-white font-medium mb-1">
                  {strategy.type === 'charge' ? '⚡ Charge' : '💰 Discharge'}
                </div>
                <div className="text-xs text-gray-300">
                  +€{strategy.profit}
                </div>
              </div>

              {/* Tooltip */}
              {hoveredIndex === index && (
                <div className="absolute top-full mt-2 left-1/2 transform -translate-x-1/2 bg-gray-900 border border-white/20 rounded-lg p-3 text-sm whitespace-nowrap z-10">
                  <div className="text-white mb-1">{strategy.time}</div>
                  <div className="text-green-400">Expected: €{strategy.profit}</div>
                  <div className="text-blue-400">Z-score: {strategy.zscore}</div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-6 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded bg-blue-500/50 border border-blue-500"></div>
          <span className="text-gray-400">Charging</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded bg-green-500/50 border border-green-500"></div>
          <span className="text-gray-400">Discharging</span>
        </div>
      </div>
    </div>
  );
}
