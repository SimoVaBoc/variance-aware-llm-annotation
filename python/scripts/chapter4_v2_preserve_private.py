"""Preserve private empirical subtrees by byte copy, verified by SHA-256.

This tool moves nothing and deletes nothing. ``copy`` makes a byte-identical
copy of named subtrees (``data``, ``runs``) into a private root outside the
repository, then re-hashes both sides and refuses to report success unless every
path, size and digest agrees. ``verify`` re-hashes a tree against an inventory
written earlier.

It never opens a file except to hash its bytes, and it prints only counts and
digests, never a record or a file name from the private trees. Existing targets
are never overwritten: preservation copies are evidence and must not change
silently.

Usage (PowerShell, from the repository root)::

    python python/scripts/chapter4_v2_preserve_private.py copy `
        --source-root . --target-root ..\\Codice_tesi_private --subtree data --subtree runs
    python python/scripts/chapter4_v2_preserve_private.py verify `
        --root ..\\Codice_tesi_private --inventory ..\\Codice_tesi_private\\preservation\\<file>.tsv
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
from pathlib import Path

INVENTORY_HEADER = "path\tsize_bytes\tsha256\n"


class PreservationError(RuntimeError):
    """A copy or an inventory does not reproduce byte for byte."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root: Path, subtrees: list[str]) -> list[tuple[str, int, str]]:
    """Relative path, size and digest of every file under the named subtrees."""

    rows: list[tuple[str, int, str]] = []
    for sub in subtrees:
        base = root / sub
        if not base.is_dir():
            raise PreservationError(f"subtree {sub!r} is not a directory under {root}")
        for path in sorted(base.rglob("*")):
            if path.is_file():
                rows.append((path.relative_to(root).as_posix(), path.stat().st_size,
                             sha256_file(path)))
    return rows


def inventory_body(rows: list[tuple[str, int, str]]) -> str:
    return "".join(f"{rel}\t{size}\t{digest}\n" for rel, size, digest in rows)


def read_inventory(path: Path) -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    seen_header = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        if not seen_header:
            if line + "\n" != INVENTORY_HEADER:
                raise PreservationError(f"{path} does not start with the inventory header")
            seen_header = True
            continue
        rel, size, digest = line.split("\t")
        rows.append((rel, int(size), digest))
    return rows


def write_inventory(path: Path, rows: list[tuple[str, int, str]], root: Path,
                    subtrees: list[str]) -> str:
    if path.exists():
        raise PreservationError(f"refusing to overwrite {path}")
    body = inventory_body(rows)
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    header = (
        f"# sha256 inventory; created_utc={_now()}\n"
        f"# root={root.resolve()}\n# subtrees={','.join(subtrees)}\n"
        f"# n_files={len(rows)}\n# total_bytes={sum(r[1] for r in rows)}\n"
        f"# body_sha256={body_hash}\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + INVENTORY_HEADER + body, encoding="utf-8", newline="\n")
    return body_hash


def compare(expected: list[tuple[str, int, str]], observed: list[tuple[str, int, str]]) -> dict:
    exp, obs = {r[0]: r[1:] for r in expected}, {r[0]: r[1:] for r in observed}
    return {
        "n_expected": len(exp),
        "n_observed": len(obs),
        "n_missing": len(set(exp) - set(obs)),
        "n_unexpected": len(set(obs) - set(exp)),
        "n_different": sum(1 for k in set(exp) & set(obs) if exp[k] != obs[k]),
    }


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _identical(summary: dict) -> bool:
    return (summary["n_missing"] == summary["n_unexpected"] == summary["n_different"] == 0
            and summary["n_expected"] == summary["n_observed"])


def cmd_copy(args: argparse.Namespace) -> int:
    source, target = Path(args.source_root).resolve(), Path(args.target_root).resolve()
    if target == source or source in target.parents:
        raise PreservationError("the private root must lie outside the source tree")
    for sub in args.subtree:
        if (target / sub).exists():
            raise PreservationError(f"refusing to overwrite existing {target / sub}")

    before = inventory(source, args.subtree)
    for sub in args.subtree:
        shutil.copytree(source / sub, target / sub, copy_function=shutil.copy2)
    after_source = inventory(source, args.subtree)
    copied = inventory(target, args.subtree)

    source_stable = compare(before, after_source)
    copy_match = compare(before, copied)
    if not _identical(source_stable):
        raise PreservationError(f"the source changed during the copy: {source_stable}")
    if not _identical(copy_match):
        raise PreservationError(f"the copy does not reproduce the source: {copy_match}")

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    preservation = target / "preservation"
    inv_path = preservation / f"preservation_copy_inventory_{stamp}.tsv"
    body_hash = write_inventory(inv_path, copied, target, args.subtree)
    manifest = {
        "kind": "private_preservation_copy",
        "created_utc": _now(),
        "source_root": str(source),
        "target_root": str(target),
        "subtrees": args.subtree,
        "n_files": len(copied),
        "total_bytes": sum(r[1] for r in copied),
        "inventory_file": inv_path.name,
        "inventory_body_sha256": body_hash,
        "verification": {"source_unchanged_during_copy": source_stable,
                         "copy_matches_source": copy_match},
        "originals_deleted": False,
        "note": "Byte copy only; no record was opened except to hash its bytes.",
    }
    manifest_path = preservation / f"PRESERVATION_MANIFEST_{stamp}.json"
    if manifest_path.exists():
        raise PreservationError(f"refusing to overwrite {manifest_path}")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("n_files", "total_bytes",
                                               "inventory_body_sha256", "verification")},
                     indent=2, sort_keys=True))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    expected = read_inventory(Path(args.inventory))
    subtrees = sorted({rel.split("/", 1)[0] for rel, _, _ in expected})
    summary = compare(expected, inventory(root, subtrees))
    summary["identical"] = _identical(summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["identical"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_copy = sub.add_parser("copy", help="byte-copy subtrees to a private root and verify")
    p_copy.add_argument("--source-root", required=True)
    p_copy.add_argument("--target-root", required=True)
    p_copy.add_argument("--subtree", action="append", required=True)
    p_copy.set_defaults(func=cmd_copy)
    p_verify = sub.add_parser("verify", help="re-hash a tree against an inventory")
    p_verify.add_argument("--root", required=True)
    p_verify.add_argument("--inventory", required=True)
    p_verify.set_defaults(func=cmd_verify)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PreservationError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
