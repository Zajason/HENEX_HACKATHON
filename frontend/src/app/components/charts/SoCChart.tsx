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
            <stop offset="5%" stopColor="#6EE7B7" stopOpacity={0.62}/>
            <stop offset="95%" stopColor="#0F1720" stopOpacity={0.04}/>
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="2 6" stroke="rgba(148,163,184,0.10)" />
        <XAxis
          dataKey="time"
          stroke="#475569"
          tick={{ fill: '#94A3B8' }}
          interval={3}
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
