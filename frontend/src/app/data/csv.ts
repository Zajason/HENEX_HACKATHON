import type { DispatchWindow, PricePoint, SocPoint, TradingSummary } from './AppDataContext';

type CsvRow = Record<string, string>;

function parseCsv(text: string) {
  const rows: string[][] = [];
  let cell = '';
  let row: string[] = [];
  let quoted = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];

    if (char === '"' && quoted && next === '"') {
      cell += '"';
      i += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === ',' && !quoted) {
      row.push(cell.trim());
      cell = '';
    } else if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && next === '\n') i += 1;
      row.push(cell.trim());
      if (row.some(Boolean)) rows.push(row);
      row = [];
      cell = '';
    } else {
      cell += char;
    }
  }

  row.push(cell.trim());
  if (row.some(Boolean)) rows.push(row);
  return rows;
}

function normalizeHeader(header: string) {
  return header.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
}

function toRows(text: string): CsvRow[] {
  const [headers, ...rows] = parseCsv(text);
  if (!headers || rows.length === 0) return [];

  const normalized = headers.map(normalizeHeader);
  return rows.map((row) =>
    normalized.reduce<CsvRow>((acc, key, index) => {
      acc[key || `column_${index}`] = row[index] ?? '';
      return acc;
    }, {}),
  );
}

function readNumber(value: string | undefined, fallback = 0) {
  if (!value) return fallback;
  const parsed = Number(value.replace(/[^0-9.-]/g, ''));
  return Number.isFinite(parsed) ? parsed : fallback;
}

function firstValue(row: CsvRow, keys: string[]) {
  for (const key of keys) {
    if (row[key] !== undefined && row[key] !== '') return row[key];
  }

  return undefined;
}

function formatTimeLabel(value: string, fallback: string) {
  if (!value) return fallback;
  const timeMatch = value.match(/\b(\d{2}:\d{2})(?::\d{2})?\b/);
  return timeMatch?.[1] ?? value;
}

export function parsePriceCsv(text: string): PricePoint[] {
  const seen = new Set<string>();

  return toRows(text)
    .map((row, index) => {
      const rawTime = firstValue(row, ['time', 'hour', 'date', 'datetime', 'timestamp', 'delivery_mtu']) ?? String(index);
      return {
        time: formatTimeLabel(rawTime, String(index)),
        actual: readNumber(firstValue(row, ['actual', 'price', 'day_ahead_price', 'dam_price_eur_mwh', 'value', 'eur_mwh'])),
        forecast: readNumber(firstValue(row, ['forecast', 'predicted', 'prediction']), NaN),
      };
    })
    .filter((point) => {
      if (seen.has(point.time)) return false;
      seen.add(point.time);
      return true;
    })
    .map((point) => ({
      ...point,
      forecast: Number.isFinite(point.forecast) ? point.forecast : undefined,
    }));
}

export function parseSocCsv(text: string): SocPoint[] {
  return toRows(text).map((row, index) => ({
    time: firstValue(row, ['time', 'hour', 'date', 'datetime', 'timestamp']) ?? String(index),
    soc: readNumber(firstValue(row, ['soc', 'state_of_charge', 'state_of_charge_percent', 'value', 'percent'])),
  }));
}

export function parseDispatchCsv(text: string): DispatchWindow[] {
  return toRows(text).map((row, index) => {
    const type = normalizeHeader(firstValue(row, ['type', 'action', 'mode']) ?? 'charge');

    return {
      id: firstValue(row, ['id']) ?? `dispatch-${index}`,
      start: firstValue(row, ['start', 'start_time', 'from']) ?? '00:00',
      end: firstValue(row, ['end', 'end_time', 'to']) ?? '01:00',
      type: type.includes('discharge') || type.includes('sell') ? 'discharge' : 'charge',
      profit: readNumber(firstValue(row, ['profit', 'margin', 'expected_margin', 'value'])),
      zscore: readNumber(firstValue(row, ['zscore', 'z_score', 'confidence']), 0),
    };
  });
}

export function parseTradingSummaryCsv(text: string): TradingSummary[] {
  return toRows(text).slice(0, 1).map((row) => ({
    expectedMargin: readNumber(firstValue(row, ['expected_margin', 'expected', 'expected_profit'])),
    bookedMargin: readNumber(firstValue(row, ['booked_margin', 'booked', 'realized_margin', 'realized_profit'])),
    equivalentCycles: readNumber(firstValue(row, ['equivalent_cycles', 'cycles', 'total_cycles'])),
    efficiencyLoss: readNumber(firstValue(row, ['efficiency_loss', 'loss'])),
    expectedChange: readNumber(firstValue(row, ['expected_change', 'expected_delta', 'forecast_delta'])),
    bookedChange: readNumber(firstValue(row, ['booked_change', 'booked_delta', 'realized_delta'])),
    cycleUtilization: readNumber(firstValue(row, ['cycle_utilization', 'cycle_utilisation', 'utilization'])),
    efficiencyChange: readNumber(firstValue(row, ['efficiency_change', 'efficiency_delta'])),
  }));
}
