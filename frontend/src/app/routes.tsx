import { createBrowserRouter } from "react-router";
import { Layout } from "./components/Layout";
import { BatteryConfig } from "./components/BatteryConfig";
import { Backtest } from "./components/Backtest";
import { RealizedPnL } from "./components/RealizedPnL";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: [
      { index: true, Component: RealizedPnL },
      { path: "config", Component: BatteryConfig },
      { path: "backtest", Component: Backtest },
      { path: "realized-pnl", Component: RealizedPnL },
    ],
  },
]);
