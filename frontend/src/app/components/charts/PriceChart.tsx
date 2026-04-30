import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import type { PricePoint } from '../../data/AppDataContext';

export function PriceChart({ data }: { data: PricePoint[] }) {
  const xAxisInterval = data.length > 48 ? 7 : 3;

  return (
    <ResponsiveContainer width="100%" height={250}>
      <LineChart data={data}>
        <defs>
          <linearGradient id="chargeGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3}/>
            <stop offset="95%" stopColor="#3B82F6" stopOpacity={0}/>
          </linearGradient>
          <linearGradient id="dischargeGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#10B981" stopOpacity={0.3}/>
            <stop offset="95%" stopColor="#10B981" stopOpacity={0}/>
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="2 6" stroke="rgba(148,163,184,0.10)" />
        <XAxis
          dataKey="time"
          stroke="#475569"
          tick={{ fill: '#94A3B8' }}
          interval={xAxisInterval}
          minTickGap={24}
        />
        <YAxis
          stroke="#475569"
          tick={{ fill: '#94A3B8' }}
          label={{ value: '€/MWh', angle: -90, position: 'insideLeft', fill: '#94A3B8' }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#0F1720',
            border: '1px solid rgba(148,163,184,0.22)',
            borderRadius: '6px',
            color: '#fff'
          }}
          labelStyle={{ color: '#CBD5E1' }}
        />
        <Line
          type="monotone"
          dataKey="actual"
          stroke="#38BDF8"
          strokeWidth={2}
          dot={false}
          name="Actual Price"
        />
        <Line
          type="monotone"
          dataKey="forecast"
          stroke="#F59E0B"
          strokeWidth={2}
          strokeDasharray="5 5"
          dot={false}
          name="Forecast"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
