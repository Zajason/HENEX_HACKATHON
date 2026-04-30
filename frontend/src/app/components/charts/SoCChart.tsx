import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import type { SocPoint } from '../../data/AppDataContext';

export function SoCChart({ data }: { data: SocPoint[] }) {
  const xAxisInterval = data.length > 48 ? 7 : 3;

  return (
    <ResponsiveContainer width="100%" height={250}>
      <AreaChart data={data}>
        <defs>
          <linearGradient id="socGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#6EE7B7" stopOpacity={0.62}/>
            <stop offset="95%" stopColor="#0F1720" stopOpacity={0.04}/>
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
          label={{ value: 'SoC %', angle: -90, position: 'insideLeft', fill: '#94A3B8' }}
          domain={[0, 100]}
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
        <Area
          type="monotone"
          dataKey="soc"
          stroke="#6EE7B7"
          strokeWidth={3}
          fill="url(#socGradient)"
          name="State of Charge"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
