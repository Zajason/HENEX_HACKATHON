import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const data = [
  { time: '00:00', actual: 45, forecast: 42, zone: 'charge' },
  { time: '01:00', actual: 38, forecast: 40, zone: 'charge' },
  { time: '02:00', actual: 32, forecast: 35, zone: 'charge' },
  { time: '03:00', actual: 28, forecast: 30, zone: 'charge' },
  { time: '04:00', actual: 30, forecast: 32, zone: 'charge' },
  { time: '05:00', actual: 35, forecast: 38, zone: 'neutral' },
  { time: '06:00', actual: 42, forecast: 45, zone: 'neutral' },
  { time: '07:00', actual: 55, forecast: 52, zone: 'neutral' },
  { time: '08:00', actual: 68, forecast: 65, zone: 'neutral' },
  { time: '09:00', actual: 75, forecast: 72, zone: 'discharge' },
  { time: '10:00', actual: 82, forecast: 80, zone: 'discharge' },
  { time: '11:00', actual: 88, forecast: 85, zone: 'discharge' },
  { time: '12:00', actual: 92, forecast: 90, zone: 'discharge' },
  { time: '13:00', actual: 90, forecast: 88, zone: 'discharge' },
  { time: '14:00', actual: 85, forecast: 83, zone: 'discharge' },
  { time: '15:00', actual: 82, forecast: 80, zone: 'discharge' },
  { time: '16:00', actual: 88, forecast: 86, zone: 'discharge' },
  { time: '17:00', actual: 95, forecast: 92, zone: 'discharge' },
  { time: '18:00', actual: 105, forecast: 102, zone: 'discharge' },
  { time: '19:00', actual: 98, forecast: 95, zone: 'discharge' },
  { time: '20:00', actual: 85, forecast: 82, zone: 'neutral' },
  { time: '21:00', actual: 72, forecast: 70, zone: 'neutral' },
  { time: '22:00', actual: 60, forecast: 58, zone: 'neutral' },
  { time: '23:00', actual: 52, forecast: 50, zone: 'neutral' },
];

export function PriceChart() {
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
          interval={3}
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
