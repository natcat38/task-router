import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { RunsListPage } from "./pages/RunsListPage";
import { RunWaterfallPage } from "./pages/RunWaterfallPage";
import { ReplayPage } from "./pages/ReplayPage";
import { StatsPage } from "./pages/StatsPage";

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<RunsListPage />} />
        <Route path="/runs/:runId" element={<RunWaterfallPage />} />
        <Route path="/runs/:runId/replay" element={<ReplayPage />} />
        <Route path="/stats" element={<StatsPage />} />
      </Routes>
    </AppShell>
  );
}
