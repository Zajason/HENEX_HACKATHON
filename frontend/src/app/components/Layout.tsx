import { Outlet, Link, useLocation } from "react-router";
import { LayoutDashboard, Battery, Target, BarChart3, Settings } from "lucide-react";

export function Layout() {
  const location = useLocation();

  const navItems = [
    { path: "/", label: "Dashboard", icon: LayoutDashboard },
    { path: "/config", label: "Battery Config", icon: Battery },
    { path: "/strategy", label: "Strategy", icon: Target },
    { path: "/backtest", label: "Backtest", icon: BarChart3 },
    { path: "/settings", label: "Settings", icon: Settings },
  ];

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#0B0F14' }}>
      {/* Sidebar */}
      <aside className="border-b border-white/5 p-4 md:fixed md:left-0 md:top-0 md:h-full md:w-64 md:border-b-0 md:border-r md:p-6" style={{ backgroundColor: '#0B0F14' }}>
        <div className="mb-4 md:mb-8">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
              <Battery className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="text-white font-semibold">Battery AI</div>
              <div className="text-xs text-gray-400">Energy Trading</div>
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
                className={`flex shrink-0 items-center gap-3 rounded-xl px-4 py-3 transition-all ${
                  isActive
                    ? 'bg-gradient-to-r from-blue-500/20 to-purple-500/20 text-white border border-blue-500/30'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                <Icon className="w-5 h-5" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="mt-4 md:absolute md:bottom-6 md:left-6 md:right-6 md:mt-0">
          <div className="p-4 rounded-xl border border-white/5" style={{ backgroundColor: '#141920' }}>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></div>
              <span className="text-xs text-gray-400">System Status</span>
            </div>
            <div className="text-sm text-white">All Systems Operational</div>
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
