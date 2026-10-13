import { BrowserRouter, Route, Routes } from "react-router-dom";
import AuthGate from "./components/AuthGate";
import Layout from "./components/Layout";
import { QuickTradeProvider } from "./components/QuickTrade";
import { ToastProvider } from "./components/ui";
import { StatusProvider } from "./lib/status";
import { ThemeProvider } from "./lib/theme";
import Agent from "./pages/Agent";
import AutoTrader from "./pages/AutoTrader";
import Dashboard from "./pages/Dashboard";
import DataCenter from "./pages/DataCenter";
import Finance from "./pages/Finance";
import Knowledge from "./pages/Knowledge";
import Portfolio from "./pages/Portfolio";
import Screener from "./pages/Screener";
import Settings from "./pages/Settings";
import Stock from "./pages/Stock";

export default function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AuthGate>
        <StatusProvider>
          <BrowserRouter>
            <QuickTradeProvider>
            <Layout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/stock" element={<Stock />} />
                <Route path="/stock/:ticker" element={<Stock />} />
                <Route path="/screener" element={<Screener />} />
                <Route path="/portfolio" element={<Portfolio />} />
                <Route path="/autotrader" element={<AutoTrader />} />
                <Route path="/agent" element={<Agent />} />
                <Route path="/finance" element={<Finance />} />
                <Route path="/knowledge" element={<Knowledge />} />
                <Route path="/data" element={<DataCenter />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<Dashboard />} />
              </Routes>
            </Layout>
            </QuickTradeProvider>
          </BrowserRouter>
        </StatusProvider>
        </AuthGate>
      </ToastProvider>
    </ThemeProvider>
  );
}
