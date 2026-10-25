import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, deleteSession, formatDate, type SessionRow } from "./api";

export type DeletableSession = Pick<
  SessionRow,
  "session_uid" | "track_name" | "session_type_name" | "started_at" | "num_laps" | "starred"
>;

interface Failure {
  message: string;
  code: string | null;
  removed: string[];
  leftBehind: string[];
}

/** Case-insensitive, trimmed: the same rule the server applies. */
export function confirmationMatches(typed: string, circuit: string): boolean {
  const t = typed.trim().toLowerCase();
  return t !== "" && t === circuit.trim().toLowerCase();
}

/**
 * US7: permanent deletion of a session AND its original recording.
 *
 * The Delete button stays disabled until the circuit name has been typed. The server
 * checks the name again; nothing here is trusted. Errors are the server's own words.
 */
export function DeleteSessionDialog({
  session,
  onClose,
  onDeleted,
}: {
  session: DeletableSession;
  /** `changed` is true when a partial deletion already altered the library. */
  onClose: (changed: boolean) => void;
  /** Called once the server confirms a complete deletion. */
  onDeleted: () => void;
}) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const matches = confirmationMatches(typed, session.track_name);

  useEffect(() => {
    input.current?.focus();
  }, []);

  // Escape closes without deleting, unless a request is already in flight.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose(failure?.code === "partial_delete");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose, failure]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!matches || busy) return;
    setBusy(true);
    setFailure(null);
    try {
      await deleteSession(session.session_uid, typed.trim());
      onDeleted();
    } catch (err) {
      if (err instanceof ApiError) {
        setFailure({
          message: err.message,
          code: err.code,
          removed: err.removed,
          leftBehind: err.leftBehind,
        });
      } else {
        setFailure({
          message: err instanceof Error ? err.message : String(err),
          code: null,
          removed: [],
          leftBehind: [],
        });
      }
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <form
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-title"
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="delete-title">Delete this session permanently?</h2>

        <p className="danger-text">
          This <strong>permanently deletes the session and its original recording</strong> from this
          computer. It cannot be undone, and ingest cannot bring it back.
        </p>

        <dl className="delete-facts">
          <dt>Circuit</dt>
          <dd>{session.track_name}</dd>
          <dt>Session</dt>
          <dd>{session.session_type_name}</dd>
          <dt>Date</dt>
          <dd>{formatDate(session.started_at)}</dd>
          <dt>Laps</dt>
          <dd>{session.num_laps}</dd>
        </dl>

        {session.starred ? (
          <div className="notice-warn">
            This session is <strong>starred</strong>. Starring protects a session from automatic
            pruning, not from deletion: it will be deleted too.
          </div>
        ) : null}

        <label className="confirm-field">
          <span>
            To confirm, type the circuit name: <strong>{session.track_name}</strong>
          </span>
          <input
            ref={input}
            type="text"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            disabled={busy}
            autoComplete="off"
            spellCheck={false}
            placeholder={session.track_name}
            aria-label="Circuit name"
          />
        </label>

        {failure ? (
          <div className="error delete-error" role="alert">
            <div>{failure.message}</div>
            {failure.code === "partial_delete" || failure.leftBehind.length > 0 ? (
              <div className="delete-lists">
                {failure.removed.length > 0 ? (
                  <>
                    <div className="k">Removed</div>
                    <ul>
                      {failure.removed.map((p) => (
                        <li key={p}>{p}</li>
                      ))}
                    </ul>
                  </>
                ) : null}
                <div className="k">Left behind</div>
                {failure.leftBehind.length > 0 ? (
                  <ul>
                    {failure.leftBehind.map((p) => (
                      <li key={p}>{p}</li>
                    ))}
                  </ul>
                ) : (
                  <div className="dim">The server did not list the leftover files.</div>
                )}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="modal-actions">
          <button type="button" className="ghost-btn" onClick={() => onClose(failure?.code === "partial_delete")} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="danger-btn" disabled={!matches || busy}>
            {busy ? "Deleting…" : "Delete permanently"}
          </button>
        </div>
      </form>
    </div>
  );
}
