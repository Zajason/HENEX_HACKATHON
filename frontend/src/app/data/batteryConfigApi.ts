import type { AssetConfig } from './AppDataContext';

const batteryConfigUrl = import.meta.env.VITE_BATTERY_CONFIG_API_URL ?? 'http://127.0.0.1:8001/api/battery-config';

export async function loadBatteryConfigFromApi() {
  const response = await fetch(batteryConfigUrl);
  if (!response.ok) {
    throw new Error(`Battery config API returned ${response.status}`);
  }
  return response.json() as Promise<AssetConfig>;
}

export async function saveBatteryConfigToApi(config: AssetConfig) {
  const response = await fetch(batteryConfigUrl, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.error ?? `Battery config API returned ${response.status}`);
  }

  return response.json() as Promise<AssetConfig>;
}
