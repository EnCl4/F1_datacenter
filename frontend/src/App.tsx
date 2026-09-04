import { useEffect, useState } from "react";
import { api, type RecorderState } from "./api";
import { SessionLibrary } from "./SessionLibrary";
import { SessionDetail } from "./SessionDetail";

/**
 * FR-029: the library must say plainly when nothing is being recorded.
 *
 * The project owner chose manual start, accepting that a session driven before the
 * recorder is running cannot be recovered. This banner is the safety net for that
 * decision -- it is not decoration.
 */
function RecordingBanner({ status }: { status: RecorderState | null }) {
  if (!status) return null;

  if (!status.recording) {
    return (
      <div className="banner idle">
        <span className="dot" />
        <span>
          <strong>Not recording.</strong> Sessions you drive right now are not being captured.
        </span>
        <span className="hint">Open F1 Data Center from your desktop to start.</span>
      </div>
    );
  }

  const late = status.session?.started_late;
  return (
    <div className="banner live">
      <span className="dot" />
      <span>
        <strong>Recording</strong>
        {status.session ? ` — lap ${status.session.current_lap || 1}` : ""}
        {late ? " · started mid-session, earlier laps were not captured" : ""}
      </span>
      {status.message ? <span className="hint">{status.message}</span> : null}
    </div>
  );
}

export function App() {
  const [selected, setSelected] = useState<string | null>(null);
  const [status, setStatus] = useState<RecorderState | null>(null);
  const [total, setTotal] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = () => {
      api
        .status()
        .then((s) => !cancelled && setStatus(s))
        .catch(() => !cancelled && setStatus(null));
    };
    poll();
    const timer = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return (
    <div className="app">
      <header className="top">
        <h1>F1 Data Center</h1>
        {total !== null ? (
          <span className="count">
            {total} session{total === 1 ? "" : "s"}
          </span>
        ) : null}
      </header>

      <RecordingBanner status={status} />

      {selected ? (
        <SessionDetail uid={selected} onBack={() => setSelected(null)} />
      ) : (
        <SessionLibrary onOpen={setSelected} onTotal={setTotal} />
      )}
    </div>
  );
}
