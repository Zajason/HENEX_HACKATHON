import { Outlet, Link, useLocation } from "react-router";
import { BarChart3, Battery, Gauge, LayoutDashboard, Settings } from "lucide-react";

export function Layout() {
  const location = useLocation();

  const navItems = [
    { path: "/", label: "Live Desk", icon: LayoutDashboard },
    { path: "/config", label: "Assets", icon: Battery },
    { path: "/backtest", label: "Backtest", icon: BarChart3 },
    { path: "/settings", label: "Settings", icon: Settings },
  ];

  return (
    <div className="min-h-screen text-slate-100">
      {/* Sidebar */}
      <aside className="border-b border-slate-700/30 bg-[#090e13]/95 p-4 md:fixed md:left-0 md:top-0 md:h-full md:w-64 md:border-b-0 md:border-r md:p-5">
        <div className="mb-5 md:mb-9">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded border border-slate-600/70 bg-[#111922]">
              <Gauge className="h-4 w-4 text-[#9ed9c5]" />
            </div>
            <div>
              <div className="text-[0.95rem] font-semibold text-white">HENEX Dispatch</div>
              <div className="text-xs text-slate-500">BESS trading desk</div>
            </div>
          </div>
        </div>

        <div className="mb-2 hidden text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-slate-600 md:block">
          Workspace
        </div>
        <nav className="flex gap-2 overflow-x-auto pb-1 md:block md:space-y-1 md:overflow-visible md:pb-0">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex shrink-0 items-center gap-3 rounded-md border px-3 py-2.5 text-sm transition-all ${
                  isActive
                    ? 'border-slate-700/70 bg-[#141c24] text-white shadow-[inset_2px_0_0_#9ed9c5]'
                    : 'border-transparent text-slate-400 hover:bg-white/[0.025] hover:text-slate-200'
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="mt-4 md:absolute md:bottom-6 md:left-6 md:right-6 md:mt-0">
          <div className="surface-muted rounded-md p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="h-1.5 w-1.5 rounded-full bg-[#9ed9c5]"></div>
              <span className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-slate-500">Market link</span>
            </div>
            <div className="text-sm text-white">Feed connected</div>
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
