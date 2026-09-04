"""T004 -- constitution principle II, made mechanical.

The capture package is the only component whose failure loses data permanently, so
it is standard-library only: no third-party imports, and no imports from the rest of
f1dc either. This is asserted rather than remembered, because "we'll be careful" is
not an enforcement mechanism.

Expressed as a test rather than ruff configuration: ruff can ban specific modules,
but cannot express "anything outside the standard library" for one directory.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
CAPTURE_DIR = SRC / "f1dc" / "capture"

# Modules the capture package is permitted to import beyond the standard library.
# Adding to this list is a constitutional change, not a convenience.
#
# f1dc.wire.header earns its place: the recorder must read sessionUID to know when to
# roll to a new file, and packetId/frameIdentifier to count losses. That is reading four
# fields at fixed offsets, not interpreting a packet -- and duplicating those offsets
# inside capture/ would risk them drifting from the codecs. header.py is itself
# standard-library only, which is asserted below.
ALLOWED_FIRST_PARTY = {"f1dc.capture", "f1dc.wire.header"}


def _capture_modules() -> list[Path]:
    return sorted(CAPTURE_DIR.rglob("*.py"))


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import
                continue
            if node.module:
                roots.add(node.module)
    return roots


def test_capture_dir_exists() -> None:
    assert CAPTURE_DIR.is_dir(), f"expected capture package at {CAPTURE_DIR}"


@pytest.mark.parametrize("path", _capture_modules(), ids=lambda p: p.name)
def test_capture_imports_stdlib_only(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    offenders: list[str] = []
    for module in sorted(_imported_roots(tree)):
        root = module.split(".")[0]
        if root == "f1dc":
            if not any(module.startswith(a) for a in ALLOWED_FIRST_PARTY):
                offenders.append(f"{module} (f1dc outside capture/)")
            continue
        if root not in sys.stdlib_module_names:
            offenders.append(f"{module} (third-party)")

    assert not offenders, (
        f"{path.relative_to(SRC)} violates constitution principle II "
        f"-- capture/ must be standard library only. Offending imports: {offenders}"
    )


def test_the_one_allowed_first_party_module_is_itself_stdlib_only() -> None:
    """f1dc.wire.header is on the allowlist, so it inherits the same obligation.

    Without this, the allowlist would be a hole: header.py could grow a pyarrow import
    and drag it into the capture path.
    """
    path = SRC / "f1dc" / "wire" / "header.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    offenders = [
        module
        for module in sorted(_imported_roots(tree))
        if module.split(".")[0] not in sys.stdlib_module_names
    ]
    assert not offenders, f"wire/header.py must stay standard library only: {offenders}"
