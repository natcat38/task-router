import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, describeApiError, getRunSpans } from "../api/client";
import type { Run } from "../api/types";
import { ReplayPanel } from "../components/ReplayPanel";
import { EmptyState, ErrorState, LoadingState } from "../components/StatusStates";

/**
 * Standalone replay-and-diff surface, reached at `/runs/:runId/replay`. The
 * run-detail waterfall page (`RunWaterfallPage`) embeds the same
 * `ReplayPanel` inline as the primary surface for this feature (Product_Scope
 * §2 surface 3) -- this route is a direct link to just that panel, e.g. for
 * sharing "replay this one" without the full waterfall.
 */
export function ReplayPage() {
  const { runId } = useParams<{ runId: string }>();

  const [run, setRun] = useState<Run | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const load = useCallback(() => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    setNotFound(false);
    getRunSpans(runId)
      .then((res) => setRun(res.run))
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setError(describeApiError(err));
        }
      })
      .finally(() => setLoading(false));
  }, [runId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return <LoadingState message="Reading trace…" />;
  }

  if (notFound) {
    return <EmptyState message="No run with this ID. It may have aged out or the ID is wrong." />;
  }

  if (error || !run) {
    return <ErrorState message={error ?? "Something went wrong."} onRetry={load} />;
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-[22px] font-semibold">Replay</h1>
      <ReplayPanel sourceRunId={run.run_id} sourceRun={run} />
    </div>
  );
}
