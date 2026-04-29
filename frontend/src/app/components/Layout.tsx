import { Outlet, Link, useLocation } from "react-router";
import { BarChart3, Battery, Gauge, LayoutDashboard, Settings, Target } from "lucide-react";

export function Layout() {
  const location = useLocation();

  const navItems = [
    { path: "/", label: "Live Desk", icon: LayoutDashboard },
    { path: "/config", label: "Assets", icon: Battery },
    { path: "/strategy", label: "Dispatch Plan", icon: Target },
    { path: "/backtest", label: "Backtest", icon: BarChart3 },
    { path: "/settings", label: "Settings", icon: Settings },
  ];

  return (
    <div className="min-h-screen bg-[#080c10] text-slate-100">
      {/* Sidebar */}
      <aside className="border-b border-slate-700/30 bg-[#0b1016] p-4 md:fixed md:left-0 md:top-0 md:h-full md:w-64 md:border-b-0 md:border-r md:p-6">
        <div className="mb-4 md:mb-8">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md border border-emerald-300/30 bg-emerald-300/10">
              <Gauge className="h-5 w-5 text-emerald-200" />
            </div>
            <div>
              <div className="font-semibold text-white">HENEX Dispatch</div>
              <div className="text-xs text-slate-400">Battery trading desk</div>
            </div>
          </div>
        </div>

        <nav className="flex gap-2 overflow-x-auto pb-1 md:block md:space-y-2 md:overflow-visible md:pb-0">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex shrink-0 items-center gap-3 rounded-lg border px-4 py-3 text-sm transition-all ${
                  isActive
                    ? 'border-emerald-300/30 bg-emerald-300/10 text-white shadow-[inset_3px_0_0_rgba(110,231,183,0.7)]'
                    : 'border-transparent text-slate-400 hover:border-slate-700/70 hover:bg-white/[0.03] hover:text-white'
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="mt-4 md:absolute md:bottom-6 md:left-6 md:right-6 md:mt-0">
          <div className="surface-muted rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="h-2 w-2 rounded-full bg-emerald-300"></div>
              <span className="text-xs uppercase tracking-wide text-slate-500">Market link</span>
            </div>
            <div className="text-sm text-white">Forecasts synced</div>
            <div className="mt-1 text-xs text-slate-500">Last update 08:45 EET</div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <div className="min-h-screen md:ml-64">
        <Outlet />
      </div>
    </div>
  );
}
