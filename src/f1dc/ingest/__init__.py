"""Ingest: raw logs in, derived rows out.

Runs in its own process, never inside the recorder (constitution principle II and VII).
Re-running it over an unchanged raw log produces identical output, which is what makes
reprocessing history routine rather than risky.
"""

from __future__ import annotations

#: Bumped whenever ingest would produce different output from the same raw log.
#: `f1dc ingest --all` re-processes anything whose stored version is older, which is how
#: a parser improvement reaches sessions recorded months ago (FR-016).
INGEST_VERSION = "1.0.0"
