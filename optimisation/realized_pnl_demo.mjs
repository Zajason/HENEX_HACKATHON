// Demo evaluator — produces realized_pnl_mtu.csv + realized_pnl_summary.csv
// from the existing tier_final schedule and battery config.
// Mirrors the logic in optimisation/realized_pnl.py so the frontend can
// render real data without needing a Python toolchain installed.

import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');

const SCHEDULE = join(ROOT, 'optimisation', 'results', 'tier_final_schedule.csv');
const CONFIG = join(ROOT, 'api', 'data', 'battery_config.json');
const MTU_OUT = join(ROOT, 'optimisation', 'results', 'realized_pnl_mtu.csv');
const SUM_OUT = join(ROOT, 'optimisation', 'results', 'realized_pnl_summary.csv');

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  const header = lines[0].split(',');
  return lines.slice(1).map((line) => {
    const cells = line.split(',');
    const row = {};
    header.forEach((h, i) => { row[h] = cells[i]; });
    return row;
  });
}

function num(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function loadBatteryParams() {
  const cfg = JSON.parse(readFileSync(CONFIG, 'utf8'));
  let totalCap = 0, totalPwr = 0;
  let wEtaCh = 0, wEtaDis = 0, wMin = 0, wMax = 0, wInit = 0, wDeg = 0;
  for (const b of cfg.batteries) {
    const qty = b.quantity ?? 1;
    const cap = (b.capacity ?? 10) * qty;
    const pwr = (b.power ?? 5) * qty;
    totalCap += cap;
    totalPwr += pwr;
    wEtaCh += (b.chargeEff ?? 92) * cap;
    wEtaDis += (b.dischargeEff ?? 90) * cap;
    wMin += (b.socMin ?? 10) * cap;
    wMax += (b.socMax ?? 90) * cap;
    wInit += (b.socInitial ?? 15) * cap;
    wDeg += (b.degradationCost ?? 2.5) * cap;
  }
  return {
    P_nom: totalPwr,
    E_nom: totalCap,
    dt: 0.25,
    eta_ch: (wEtaCh / totalCap) / 100,
    eta_dis: (wEtaDis / totalCap) / 100,
    SOC_min: (wMin / totalCap) / 100 * totalCap,
    SOC_max: (wMax / totalCap) / 100 * totalCap,
    E_init: (wInit / totalCap) / 100 * totalCap,
    c_deg: wDeg / totalCap,
    max_cycles: 2.0,
    grid_import_max: totalPwr,
    grid_export_max: totalPwr,
  };
}

// Mulberry32 PRNG (seeded) — keep demo actuals reproducible
function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function gauss(rand) {
  const u = 1 - rand(); const v = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function evaluate(rows, bp) {
  const rand = mulberry32(7);
  const eps = 1e-6;
  let charge_cost = 0, discharge_revenue = 0, degradation = 0;
  let throughput = 0, expected = 0, mae = 0;
  let socMin = Infinity, socMax = -Infinity;
  const violations = { soc_below: 0, soc_above: 0, simul: 0, power: 0, imp: 0, exp: 0 };

  let soc = bp.E_init;
  let cum = 0;
  const out = [];

  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    const p_ch = num(r.charge_mw);
    const p_dis = num(r.discharge_mw);
    const p50 = num(r.p50_eur_mwh);
    const p10 = num(r.p10_eur_mwh);
    const p90 = num(r.p90_eur_mwh);
    const band = (p90 - p10) / 2 || 5;
    const noise = gauss(rand) * band * 0.45;
    const actual = Math.max(-50, Math.min(600, p50 + noise));
    const dt = bp.dt;

    soc = soc + bp.eta_ch * p_ch * dt - (p_dis / bp.eta_dis) * dt;

    const cc = actual * p_ch * dt;
    const dr = actual * p_dis * dt;
    const cf = dr - cc;
    const dg = bp.c_deg * (p_ch + p_dis) * dt;
    const realized = cf - dg;

    cum += realized;
    charge_cost += cc;
    discharge_revenue += dr;
    degradation += dg;
    throughput += (p_ch + p_dis) * dt;
    expected += (p50 * (p_dis - p_ch)) * dt - bp.c_deg * (p_ch + p_dis) * dt;
    mae += Math.abs(actual - p50);
    socMin = Math.min(socMin, soc);
    socMax = Math.max(socMax, soc);

    const flags = {
      soc_below_min: soc < bp.SOC_min - eps,
      soc_above_max: soc > bp.SOC_max + eps,
      simultaneous: p_ch > eps && p_dis > eps,
      power_exceeded: p_ch > bp.P_nom + eps || p_dis > bp.P_nom + eps,
      grid_import: p_ch > bp.grid_import_max + eps,
      grid_export: p_dis > bp.grid_export_max + eps,
    };
    if (flags.soc_below_min) violations.soc_below++;
    if (flags.soc_above_max) violations.soc_above++;
    if (flags.simultaneous) violations.simul++;
    if (flags.power_exceeded) violations.power++;
    if (flags.grid_import) violations.imp++;
    if (flags.grid_export) violations.exp++;

    out.push({
      timestamp: r.timestamp,
      p50_eur_mwh: p50,
      charge_mw: p_ch,
      discharge_mw: p_dis,
      actual_price_eur_mwh: actual,
      price_error_eur_mwh: actual - p50,
      charge_cost_eur: cc,
      discharge_revenue_eur: dr,
      net_cashflow_eur: cf,
      degradation_eur: dg,
      realized_pnl_eur: realized,
      cum_realized_pnl_eur: cum,
      soc_mwh_recomputed: soc,
      soc_mwh_schedule: num(r.soc_mwh),
      flag_soc_below_min: flags.soc_below_min,
      flag_soc_above_max: flags.soc_above_max,
      flag_simultaneous: flags.simultaneous,
      flag_power_exceeded: flags.power_exceeded,
      flag_grid_import: flags.grid_import,
      flag_grid_export: flags.grid_export,
    });
  }

  const cycles = throughput / (2 * bp.E_nom);
  const realized_total = discharge_revenue - charge_cost - degradation;
  const summary = {
    delivery_day: rows.length ? rows[0].timestamp.slice(0, 10) : null,
    mtus_total: rows.length,
    mtus_missing_actual: 0,
    total_charge_cost_eur: charge_cost,
    total_discharge_revenue_eur: discharge_revenue,
    net_arbitrage_profit_eur: discharge_revenue - charge_cost,
    degradation_cost_eur: degradation,
    realized_pnl_eur: realized_total,
    expected_pnl_on_p50_eur: expected,
    forecast_vs_realized_delta_eur: realized_total - expected,
    throughput_mwh: throughput,
    equivalent_cycles: cycles,
    mean_abs_price_error_eur_mwh: mae / Math.max(rows.length, 1),
    min_soc_mwh: socMin,
    max_soc_mwh: socMax,
    violations_total:
      violations.soc_below + violations.soc_above + violations.simul +
      violations.power + violations.imp + violations.exp,
    viol_soc_below_min: violations.soc_below,
    viol_soc_above_max: violations.soc_above,
    viol_simultaneous: violations.simul,
    viol_power_exceeded: violations.power,
    viol_grid_import: violations.imp,
    viol_grid_export: violations.exp,
    cycle_limit_breach: cycles > bp.max_cycles + 1e-6,
  };
  return { mtu: out, summary };
}

function toCsv(rows) {
  if (!rows.length) return '';
  const header = Object.keys(rows[0]);
  const escape = (v) => {
    if (typeof v === 'boolean') return v ? 'True' : 'False';
    if (v === null || v === undefined) return '';
    return String(v);
  };
  return [
    header.join(','),
    ...rows.map((r) => header.map((h) => escape(r[h])).join(',')),
  ].join('\n');
}

const bp = loadBatteryParams();
const schedule = parseCsv(readFileSync(SCHEDULE, 'utf8'));
const { mtu, summary } = evaluate(schedule, bp);

writeFileSync(MTU_OUT, toCsv(mtu));
writeFileSync(SUM_OUT, toCsv([summary]));

console.log(`Wrote ${MTU_OUT}`);
console.log(`Wrote ${SUM_OUT}`);
console.log(`Realized PnL: ${summary.realized_pnl_eur.toFixed(2)} € over ${summary.mtus_total} MTUs`);
console.log(`Violations: ${summary.violations_total}`);
