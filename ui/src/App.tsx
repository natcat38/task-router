import { Link, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { RunsListPage } from "./pages/RunsListPage";
import { RunWaterfallPage } from "./pages/RunWaterfallPage";
import { ReplayPage } from "./pages/ReplayPage";
import { StatsPage } from "./pages/StatsPage";
import { EmptyState } from "./components/StatusStates";
import { useDocumentTitle } from "./lib/useDocumentTitle";

function NotFoundPage() {
  useDocumentTitle("Not found");
  return (
    <EmptyState
      message="There is no page at this address."
      action={
        <Link to="/" className="font-mono text-[13px] text-signal underline decoration-line hover:decoration-signal">
          Go to Runs
        </Link>
      }
    />
  );
}

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<RunsListPage />} />
        <Route path="/runs/:runId" element={<RunWaterfallPage />} />
        <Route path="/runs/:runId/replay" element={<ReplayPage />} />
        <Route path="/stats" element={<StatsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppShell>
  );
}
