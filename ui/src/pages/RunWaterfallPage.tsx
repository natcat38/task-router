import { useParams } from "react-router-dom";
import { Placeholder } from "../components/StatusStates";

/**
 * Span waterfall for one run (Product_Scope §2 surface 2). Data wiring
 * against GET /runs/{id}/spans lands in a later chunk.
 */
export function RunWaterfallPage() {
  const { runId } = useParams<{ runId: string }>();
  return (
    <Placeholder title={`Run ${runId ?? ""}`}>
      <p className="mt-3 font-mono text-[13px] text-fog">run_id: {runId}</p>
    </Placeholder>
  );
}
