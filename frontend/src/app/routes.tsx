import { createBrowserRouter } from "react-router";
import { Layout } from "./components/Layout";
import { Dashboard } from "./components/Dashboard";
import { BatteryConfig } from "./components/BatteryConfig";
import { Strategy } from "./components/Strategy";
import { Backtest } from "./components/Backtest";
import { Settings } from "./components/Settings";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: [
      { index: true, Component: Dashboard },
      { path: "config", Component: BatteryConfig },
      { path: "strategy", Component: Strategy },
      { path: "backtest", Component: Backtest },
      { path: "settings", Component: Settings },
    ],
  },
]);
