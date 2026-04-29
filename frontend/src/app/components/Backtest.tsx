import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { TrendingUp, AlertTriangle } from 'lucide-react';

const profitOverTime = [
  { date: 'Jan 1', profit: 2100 },
  { date: 'Jan 8', profit: 2450 },
  { date: 'Jan 15', profit: 2800 },
  { date: 'Jan 22', profit: 2650 },
  { date: 'Jan 29', profit: 3100 },
  { date: 'Feb 5', profit: 2900 },
  { date: 'Feb 12', profit: 3350 },
  { date: 'Feb 19', profit: 3800 },
  { date: 'Feb 26', profit: 3500 },
  { date: 'Mar 5', profit: 4200 },
  { date: 'Mar 12', profit: 3900 },
  { date: 'Mar 19', profit: 4500 },
];

const dailyProfitDistribution = [
  { range: '0-500', count: 12 },
  { range: '500-1000', count: 25 },
  { range: '1000-1500', count: 35 },
  { range: '1500-2000', count: 45 },
  { range: '2000-2500', count: 52 },
  { range: '2500-3000', count: 38 },
  { range: '3000-3500', count: 22 },
  { range: '3500+', count: 15 },
];

const drawdownData = [
  { date: 'Week 1', drawdown: 0 },
  { date: 'Week 2', drawdown: -150 },
  { date: 'Week 3', drawdown: -80 },
  { date: 'Week 4', drawdown: -220 },
  { date: 'Week 5', drawdown: -100 },
  { date: 'Week 6', drawdown: -380 },
  { date: 'Week 7', drawdown: -200 },
  { date: 'Week 8', drawdown: -120 },
  { date: 'Week 9', drawdown: -290 },
  { date: 'Week 10', drawdown: -150 },
  { date: 'Week 11', drawdown: -90 },
  { date: 'Week 12', drawdown: -50 },
];

export function Backtest() {
  return (
    <div className="p-4 md:p-8">
      <div className="mb-8">
        <h1 className="text-3xl text-white mb-2">Backtest Results</h1>
        <p className="text-gray-400">Historical performance analysis (Last 90 days)</p>
      </div>

      {/* Summary Cards */}
      <div className="mb-6 grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-white/5 p-6 backdrop-blur-xl" style={{ backgroundColor: 'rgba(20, 25, 32, 0.6)' }}>
          <div className="text-sm text-gray-400 mb-2">Total Profit</div>
          <div className="text-2xl text-white mb-2">€308,450</div>
          <div className="flex items-center gap-1 text-xs text-green-400">
            <TrendingUp className="w-3 h-3" />
            +15.2% vs forecast
          </div>
        </div>

        <div className="rounded-2xl border border-white/5 p-6 backdrop-blur-xl" style={{ backgroundColor: 'rgba(20, 25, 32, 0.6)' }}>
          <div className="text-sm text-gray-400 mb-2">Avg Daily Profit</div>
          <div className="text-2xl text-white mb-2">€3,427</div>
          <div className="flex items-center gap-1 text-xs text-green-400">
            <TrendingUp className="w-3 h-3" />
            +8.4% improvement
          </div>
        </div>

        <div className="rounded-2xl border border-white/5 p-6 backdrop-blur-xl" style={{ backgroundColor: 'rgba(20, 25, 32, 0.6)' }}>
          <div className="text-sm text-gray-400 mb-2">Win Rate</div>
          <div className="text-2xl text-white mb-2">87.3%</div>
          <div className="flex items-center gap-1 text-xs text-blue-400">
            <TrendingUp className="w-3 h-3" />
            262 / 300 trades
          </div>
        </div>

        <div className="rounded-2xl border border-white/5 p-6 backdrop-blur-xl" style={{ backgroundColor: 'rgba(20, 25, 32, 0.6)' }}>
          <div className="text-sm text-gray-400 mb-2">Max Drawdown</div>
          <div className="text-2xl text-white mb-2">€380</div>
          <div className="flex items-center gap-1 text-xs text-yellow-400">
            <AlertTriangle className="w-3 h-3" />
            -0.12% of total
          </div>
        </div>
      </div>

      {/* Charts Row 1 */}
      <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <div className="rounded-2xl border border-white/5 p-6 backdrop-blur-xl" style={{ backgroundColor: 'rgba(20, 25, 32, 0.6)' }}>
          <h3 className="text-white mb-4">Cumulative Profit Over Time</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={profitOverTime}>
              <defs>
                <linearGradient id="profitLineGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10B981" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#10B981" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="date" stroke="#6B7280" tick={{ fill: '#9CA3AF' }} />
              <YAxis stroke="#6B7280" tick={{ fill: '#9CA3AF' }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: '8px',
                  color: '#fff'
                }}
              />
              <Line
                type="monotone"
                dataKey="profit"
                stroke="#10B981"
                strokeWidth={3}
                dot={{ fill: '#10B981', r: 4 }}
                fill="url(#profitLineGradient)"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-2xl border border-white/5 p-6 backdrop-blur-xl" style={{ backgroundColor: 'rgba(20, 25, 32, 0.6)' }}>
          <h3 className="text-white mb-4">Daily Profit Distribution</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={dailyProfitDistribution}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="range" stroke="#6B7280" tick={{ fill: '#9CA3AF' }} />
              <YAxis stroke="#6B7280" tick={{ fill: '#9CA3AF' }} label={{ value: 'Days', angle: -90, position: 'insideLeft', fill: '#9CA3AF' }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: '8px',
                  color: '#fff'
                }}
              />
              <Bar dataKey="count" fill="#3B82F6" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Drawdown Chart */}
      <div className="rounded-2xl border border-white/5 p-6 backdrop-blur-xl" style={{ backgroundColor: 'rgba(20, 25, 32, 0.6)' }}>
        <h3 className="text-white mb-4">Worst-Case Drawdown Analysis</h3>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={drawdownData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey="date" stroke="#6B7280" tick={{ fill: '#9CA3AF' }} />
            <YAxis stroke="#6B7280" tick={{ fill: '#9CA3AF' }} label={{ value: '€', angle: -90, position: 'insideLeft', fill: '#9CA3AF' }} />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1F2937',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '8px',
                color: '#fff'
              }}
            />
            <Line
              type="monotone"
              dataKey="drawdown"
              stroke="#EF4444"
              strokeWidth={2}
              dot={{ fill: '#EF4444', r: 3 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
