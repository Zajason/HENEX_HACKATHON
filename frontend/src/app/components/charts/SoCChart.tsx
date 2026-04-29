import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const data = [
  { time: '00:00', soc: 50 },
  { time: '01:00', soc: 55 },
  { time: '02:00', soc: 62 },
  { time: '03:00', soc: 70 },
  { time: '04:00', soc: 78 },
  { time: '05:00', soc: 82 },
  { time: '06:00', soc: 85 },
  { time: '07:00', soc: 85 },
  { time: '08:00', soc: 85 },
  { time: '09:00', soc: 78 },
  { time: '10:00', soc: 70 },
  { time: '11:00', soc: 62 },
  { time: '12:00', soc: 52 },
  { time: '13:00', soc: 42 },
  { time: '14:00', soc: 35 },
  { time: '15:00', soc: 28 },
  { time: '16:00', soc: 20 },
  { time: '17:00', soc: 12 },
  { time: '18:00', soc: 5 },
  { time: '19:00', soc: 8 },
  { time: '20:00', soc: 15 },
  { time: '21:00', soc: 22 },
  { time: '22:00', soc: 30 },
  { time: '23:00', soc: 38 },
];

export function SoCChart() {
  return (
    <ResponsiveContainer width="100%" height={250}>
      <AreaChart data={data}>
        <defs>
          <linearGradient id="socGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.8}/>
            <stop offset="95%" stopColor="#8B5CF6" stopOpacity={0.1}/>
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis
          dataKey="time"
          stroke="#6B7280"
          tick={{ fill: '#9CA3AF' }}
          interval={3}
        />
        <YAxis
          stroke="#6B7280"
          tick={{ fill: '#9CA3AF' }}
          label={{ value: 'SoC %', angle: -90, position: 'insideLeft', fill: '#9CA3AF' }}
          domain={[0, 100]}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1F2937',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '8px',
            color: '#fff'
          }}
          labelStyle={{ color: '#9CA3AF' }}
        />
        <Area
          type="monotone"
          dataKey="soc"
          stroke="#3B82F6"
          strokeWidth={3}
          fill="url(#socGradient)"
          name="State of Charge"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
