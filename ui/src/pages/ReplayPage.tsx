import { useParams } from "react-router-dom";
import { Placeholder } from "../components/StatusStates";

/**
 * Replay-and-diff for one run (Product_Scope §2 surface 3). Data wiring
 * against POST /replay lands in a later chunk.
 */
export function ReplayPage() {
  const { runId } = useParams<{ runId: string }>();
  return (
    <Placeholder title={`Replay ${runId ?? ""}`}>
      <p className="mt-3 font-mono text-[13px] text-fog">source_run_id: {runId}</p>
    </Placeholder>
  );
}
