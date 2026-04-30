/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { loadBatteryConfigFromApi, saveBatteryConfigToApi } from './batteryConfigApi';
import { parsePriceCsv } from './csv';
import { dayAheadPriceCsv } from './priceCurveSource';

export type PricePoint = {
  time: string;
  actual: number;
  forecast?: number;
};

export type SocPoint = {
  time: string;
  soc: number;
};

export type DispatchWindow = {
  id: string;
  start: string;
  end: string;
  type: 'charge' | 'discharge';
  profit: number;
  zscore: number;
};

export type TradingSummary = {
  expectedMargin: number;
  bookedMargin: number;
  equivalentCycles: number;
  efficiencyLoss: number;
  expectedChange: number;
  bookedChange: number;
  cycleUtilization: number;
  efficiencyChange: number;
};

export type BatteryUnitConfig = {
  id: string;
  name: string;
  quantity: number;
  capacity: number;
  power: number;
  socMin: number;
  socMax: number;
  socInitial: number;
  chargeEff: number;
  dischargeEff: number;
  degradationCost: number;
};

export type AssetConfig = {
  batteries: BatteryUnitConfig[];
};

const assetConfigKey = 'henex.assetConfig.v1';

const fallbackPriceData: PricePoint[] = [
  { time: '00:00', actual: 45, forecast: 42 },
  { time: '01:00', actual: 38, forecast: 40 },
  { time: '02:00', actual: 32, forecast: 35 },
  { time: '03:00', actual: 28, forecast: 30 },
  { time: '04:00', actual: 30, forecast: 32 },
  { time: '05:00', actual: 35, forecast: 38 },
  { time: '06:00', actual: 42, forecast: 45 },
  { time: '07:00', actual: 55, forecast: 52 },
  { time: '08:00', actual: 68, forecast: 65 },
  { time: '09:00', actual: 75, forecast: 72 },
  { time: '10:00', actual: 82, forecast: 80 },
  { time: '11:00', actual: 88, forecast: 85 },
  { time: '12:00', actual: 92, forecast: 90 },
  { time: '13:00', actual: 90, forecast: 88 },
  { time: '14:00', actual: 85, forecast: 83 },
  { time: '15:00', actual: 82, forecast: 80 },
  { time: '16:00', actual: 88, forecast: 86 },
  { time: '17:00', actual: 95, forecast: 92 },
  { time: '18:00', actual: 105, forecast: 102 },
  { time: '19:00', actual: 98, forecast: 95 },
  { time: '20:00', actual: 85, forecast: 82 },
  { time: '21:00', actual: 72, forecast: 70 },
  { time: '22:00', actual: 60, forecast: 58 },
  { time: '23:00', actual: 52, forecast: 50 },
];

const parsedPriceData = parsePriceCsv(dayAheadPriceCsv);
export const defaultPriceData: PricePoint[] = parsedPriceData.length > 0 ? parsedPriceData : fallbackPriceData;

export const defaultSocData: SocPoint[] = [
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

export const defaultDispatchWindows: DispatchWindow[] = [
  { id: 'charge-overnight', start: '02:00', end: '06:00', type: 'charge', profit: 245, zscore: 2.1 },
  { id: 'sell-morning', start: '09:00', end: '13:00', type: 'discharge', profit: 890, zscore: 2.8 },
  { id: 'sell-evening', start: '15:00', end: '19:00', type: 'discharge', profit: 1240, zscore: 3.2 },
];

export const defaultAssetConfig: AssetConfig = {
  batteries: [
    {
      id: 'battery-1',
      name: 'Battery block 1',
      quantity: 1,
      capacity: 10,
      power: 5,
      socMin: 10,
      socMax: 90,
      socInitial: 15,
      chargeEff: 92,
      dischargeEff: 90,
      degradationCost: 2.5,
    },
  ],
};

const defaultTradingSummary: TradingSummary = {
  expectedMargin: 2375,
  bookedMargin: 2240,
  equivalentCycles: 147,
  efficiencyLoss: 5.7,
  expectedChange: 12.5,
  bookedChange: 8.2,
  cycleUtilization: 94.2,
  efficiencyChange: -2.1,
};

type AppDataContextValue = {
  priceData: PricePoint[];
  setPriceData: (data: PricePoint[]) => void;
  socData: SocPoint[];
  setSocData: (data: SocPoint[]) => void;
  dispatchWindows: DispatchWindow[];
  setDispatchWindows: (data: DispatchWindow[]) => void;
  tradingSummary: TradingSummary;
  setTradingSummary: (data: TradingSummary) => void;
  assetConfig: AssetConfig;
  saveAssetConfig: (config: AssetConfig) => Promise<void>;
};

const AppDataContext = createContext<AppDataContextValue | null>(null);

function loadAssetConfig() {
  if (typeof window === 'undefined') return defaultAssetConfig;

  try {
    const saved = window.localStorage.getItem(assetConfigKey);
    if (!saved) return defaultAssetConfig;

    const parsed = JSON.parse(saved);
    if (Array.isArray(parsed?.batteries)) {
      return {
        batteries: parsed.batteries.map((battery: Partial<BatteryUnitConfig>, index: number) => ({
          id: battery.id ?? `battery-${index + 1}`,
          name: battery.name ?? `Battery block ${index + 1}`,
          quantity: battery.quantity ?? 1,
          capacity: battery.capacity ?? 10,
          power: battery.power ?? 5,
          socMin: battery.socMin ?? 10,
          socMax: battery.socMax ?? 90,
          socInitial: battery.socInitial ?? 15,
          chargeEff: battery.chargeEff ?? 92,
          dischargeEff: battery.dischargeEff ?? 90,
          degradationCost: battery.degradationCost ?? 2.5,
        })),
      };
    }

    if (typeof parsed?.batteries === 'number') {
      return {
        batteries: [
          {
            id: 'battery-block-1',
            name: 'Battery block 1',
            quantity: Math.max(parsed.batteries, 1),
            capacity: parsed.capacity ?? 10,
            power: parsed.power ?? 5,
            socMin: parsed.socMin ?? 10,
            socMax: parsed.socMax ?? 90,
            socInitial: parsed.socInitial ?? 15,
            chargeEff: parsed.chargeEff ?? 92,
            dischargeEff: parsed.dischargeEff ?? 90,
            degradationCost: parsed.degradationCost ?? 2.5,
          },
        ],
      };
    }

    return defaultAssetConfig;
  } catch {
    return defaultAssetConfig;
  }
}

export function AppDataProvider({ children }: { children: ReactNode }) {
  const [priceData, setPriceData] = useState(defaultPriceData);
  const [socData, setSocData] = useState(defaultSocData);
  const [dispatchWindows, setDispatchWindows] = useState(defaultDispatchWindows);
  const [tradingSummary, setTradingSummary] = useState(defaultTradingSummary);
  const [assetConfig, setAssetConfig] = useState(loadAssetConfig);

  useEffect(() => {
    window.localStorage.setItem(assetConfigKey, JSON.stringify(assetConfig));
  }, [assetConfig]);

  useEffect(() => {
    let cancelled = false;

    loadBatteryConfigFromApi()
      .then((config) => {
        if (!cancelled) setAssetConfig(config);
      })
      .catch(() => {
        // The frontend remains usable without the optional local API server.
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const saveAssetConfig = useCallback(async (config: AssetConfig) => {
    const savedConfig = await saveBatteryConfigToApi(config);
    setAssetConfig(savedConfig);
  }, []);

  const value = useMemo(
    () => ({
      priceData,
      setPriceData,
      socData,
      setSocData,
      dispatchWindows,
      setDispatchWindows,
      tradingSummary,
      setTradingSummary,
      assetConfig,
      saveAssetConfig,
    }),
    [assetConfig, dispatchWindows, priceData, saveAssetConfig, socData, tradingSummary],
  );

  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}

// Later optimization/API code can call these setters from useAppData():
// setPriceData(pricePoints), setSocData(socPoints),
// setDispatchWindows(windows), and setTradingSummary(summary).
// Keep CSV parsing outside the dashboard UI; src/app/data/csv.ts is only a code-level adapter.

export function useAppData() {
  const value = useContext(AppDataContext);
  if (!value) {
    throw new Error('useAppData must be used inside AppDataProvider');
  }
  return value;
}
