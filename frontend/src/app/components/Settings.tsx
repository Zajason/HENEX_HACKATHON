import { Bell, Shield, Database } from 'lucide-react';

function Switch({ checked = false }: { checked?: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={checked}
      className={`relative h-6 w-11 rounded-full border transition-colors ${
        checked
          ? 'border-[#9ed9c5]/70 bg-[#9ed9c5]/20'
          : 'border-slate-600 bg-slate-900/70'
      }`}
    >
      <span
        className={`absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full transition-transform ${
          checked
            ? 'translate-x-[21px] bg-[#bcebdc]'
            : 'translate-x-1 bg-slate-500'
        }`}
      />
    </button>
  );
}

function SettingsSection({
  title,
  description,
  icon: Icon,
  children,
}: {
  title: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <section className="grid gap-4 border-t border-slate-700/50 py-6 lg:grid-cols-[220px_minmax(0,1fr)]">
      <div>
        <div className="mb-2 flex items-center gap-2 text-white">
          <Icon className="h-4 w-4 text-[#9ed9c5]" />
          <h2 className="section-kicker">{title}</h2>
        </div>
        <p className="quiet-note max-w-xs">{description}</p>
      </div>
      <div className="surface rounded-md p-5">{children}</div>
    </section>
  );
}

export function Settings() {
  return (
    <div className="mx-auto max-w-6xl p-4 md:p-8">
      <div className="mb-7 border-b border-slate-700/50 pb-6">
        <div className="mb-3 text-sm text-slate-500">Desk controls / Settings</div>
        <h1 className="mb-2 text-3xl font-semibold leading-tight text-white">Settings</h1>
        <p className="max-w-2xl text-slate-400">
          Keep the trading loop predictable: alerts, guardrails, data feeds, and model cadence.
        </p>
      </div>

      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_280px]">
        <div>
          <SettingsSection
            title="Notifications"
            description="Only surface events that a trader would actually interrupt their flow for."
            icon={Bell}
          >
            <div className="control-row">
              <div>
                <div className="mb-1 text-white">Trade execution alerts</div>
                <div className="quiet-note">Notify when a scheduled charge or discharge order is confirmed.</div>
              </div>
              <Switch checked />
            </div>
            <div className="control-row">
              <div>
                <div className="mb-1 text-white">Price spike warnings</div>
                <div className="quiet-note">Flag sudden EUR/MWh moves outside the current forecast band.</div>
              </div>
              <Switch checked />
            </div>
            <div className="control-row">
              <div>
                <div className="mb-1 text-white">Daily performance summary</div>
                <div className="quiet-note">Send a concise end-of-day margin and cycle report.</div>
              </div>
              <Switch />
            </div>
          </SettingsSection>

          <SettingsSection
            title="Risk"
            description="Hard stops used before the dispatch plan is allowed onto the desk."
            icon={Shield}
          >
            <div className="grid gap-4 md:grid-cols-3">
              <label>
                <span className="mb-2 block text-sm text-slate-400">Maximum daily loss</span>
                <div className="relative">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500">€</span>
                  <input type="number" defaultValue={5000} className="field-control pl-7" />
                </div>
              </label>
              <label>
                <span className="mb-2 block text-sm text-slate-400">Minimum z-score</span>
                <input type="number" step="0.1" defaultValue={2.5} className="field-control" />
              </label>
              <label>
                <span className="mb-2 block text-sm text-slate-400">Minimum spread</span>
                <div className="relative">
                  <input type="number" defaultValue={20} className="field-control pr-16" />
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-500">€/MWh</span>
                </div>
              </label>
            </div>
          </SettingsSection>

          <SettingsSection
            title="Data"
            description="The sources and refresh cadence that feed forecasts and backtests."
            icon={Database}
          >
            <div className="grid gap-4 md:grid-cols-3">
              <label>
                <span className="mb-2 block text-sm text-slate-400">Price source</span>
                <select className="field-control">
                  <option>EPEX SPOT</option>
                  <option>Nord Pool</option>
                  <option>OMIE</option>
                </select>
              </label>
              <label>
                <span className="mb-2 block text-sm text-slate-400">Forecast model</span>
                <select className="field-control">
                  <option>LSTM baseline</option>
                  <option>XGBoost spread model</option>
                  <option>Prophet benchmark</option>
                </select>
              </label>
              <label>
                <span className="mb-2 block text-sm text-slate-400">Refresh cadence</span>
                <select className="field-control">
                  <option>15 minutes</option>
                  <option>30 minutes</option>
                  <option>1 hour</option>
                </select>
              </label>
            </div>
          </SettingsSection>

          <div className="flex justify-end border-t border-slate-700/50 pt-6">
            <button className="rounded-md border border-[#9ed9c5]/50 bg-[#9ed9c5]/12 px-5 py-2.5 text-sm font-semibold text-[#d9fff2] transition-colors hover:bg-[#9ed9c5]/18">
              Save changes
            </button>
          </div>
        </div>

        <aside className="surface-muted h-fit rounded-md p-5 xl:sticky xl:top-6">
          <div className="mb-4 text-sm font-semibold text-white">Current run</div>
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">Market</dt>
              <dd className="text-slate-200">HENEX DAM</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">Asset</dt>
              <dd className="text-slate-200">40 MWh</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">Next refresh</dt>
              <dd className="text-slate-200">09:00 EET</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-slate-500">Guardrail</dt>
              <dd className="text-[#bcebdc]">Active</dd>
            </div>
          </dl>
          <div className="mt-5 border-t border-slate-700/50 pt-4 text-xs leading-relaxed text-slate-500">
            Changes apply to the next dispatch calculation. Existing scheduled trades stay untouched.
          </div>
        </aside>
      </div>
    </div>
  );
}
