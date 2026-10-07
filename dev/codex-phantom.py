#!/usr/bin/env python3
"""Inspect and safely repair phantom history in local Codex tasks.

A supported phantom state is a paginated task whose SQLite projection stopped
because the unprojected JSONL tail repeats the immediately preceding ordinal
for a ``thread_settings_applied`` event.  Repair never deletes projected rows:
it creates a canonical-name normalized rollout copy and lets Codex append the
previously blocked tail on the next resume.

This operates on undocumented Codex internals. Always keep the generated
backup directory until the repaired task has been thoroughly checked.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import colorsys

RESET = "\033[0m"

BLACK = "\033[30m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"

BRIGHT_BLACK = "\033[90m"
BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN = "\033[96m"
BRIGHT_WHITE = "\033[97m"

BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"


HISTORY_TABLES = (
    "thread_realtime_items",
    "thread_items",
    "thread_turns",
    "thread_history_projection_state",
)
CANONICAL_RE = re.compile(
    r"^rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-"
    r"(?P<thread_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$"
)


class PhantomError(RuntimeError):
    pass


@dataclass
class ThreadInfo:
    id: str
    name: str
    title: str
    preview: str
    rollout_path: str
    history_mode: str
    archived: bool
    updated_at: int
    cwd: str


@dataclass
class Duplicate:
    byte_offset: int
    ordinal: int
    payload_type: str


@dataclass
class ScanResult:
    status: str
    detail: str
    file_size: int | None = None
    projection_offset: int | None = None
    next_ordinal: int | None = None
    tail_bytes: int | None = None
    turns: int = 0
    items: int = 0
    duplicates: list[Duplicate] = field(default_factory=list)
    valid_tail_records: int = 0
    final_ordinal: int | None = None
    canonical_name: str | None = None
    canonical_filename: bool = False
    mismatch: dict | None = None

    @property
    def repairable(self) -> bool:
        return self.status in {"phantom", "invalid-name", "phantom+invalid-name"}


def connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    else:
        db = sqlite3.connect(path, timeout=30)
    db.execute("PRAGMA busy_timeout = 30000")
    return db


def integrity(db: sqlite3.Connection, label: str) -> None:
    result = db.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise PhantomError(f"{label}: SQLite integrity check failed: {result}")


def database_paths(codex_dir: Path) -> tuple[Path, Path]:
    state = codex_dir / "state_5.sqlite"
    history = codex_dir / "thread_history_1.sqlite"
    if not state.is_file() or not history.is_file():
        raise PhantomError(f"Expected state_5.sqlite and thread_history_1.sqlite under {codex_dir}")
    return state, history


def thread_from_row(row: sqlite3.Row) -> ThreadInfo:
    values = dict(row)
    return ThreadInfo(
        id=values["id"],
        name=values.get("name") or values.get("title") or values.get("preview") or values["id"],
        title=values.get("title") or "",
        preview=values.get("preview") or "",
        rollout_path=values.get("rollout_path") or "",
        history_mode=values.get("history_mode") or "",
        archived=bool(values.get("archived")),
        updated_at=int(values.get("updated_at") or 0),
        cwd=values.get("cwd") or "",
    )


def load_threads(state_path: Path, *, include_archived: bool = True) -> list[ThreadInfo]:
    with connect(state_path, readonly=True) as db:
        db.row_factory = sqlite3.Row
        where = "" if include_archived else "WHERE archived = 0"
        rows = db.execute(
            "SELECT id, name, title, preview, rollout_path, history_mode, "
            f"archived, updated_at, cwd FROM threads {where} ORDER BY updated_at DESC"
        ).fetchall()
    return [thread_from_row(row) for row in rows]


def display_name(thread: ThreadInfo) -> str:
    return " ".join(thread.name.split()) or thread.id


def resolve_thread(state_path: Path, selector: str) -> ThreadInfo:
    threads = load_threads(state_path)
    needle = selector.casefold()
    exact_id = [t for t in threads if t.id == selector]
    if exact_id:
        return exact_id[0]
    id_prefix = [t for t in threads if t.id.startswith(selector)]
    if len(id_prefix) == 1:
        return id_prefix[0]
    exact_name = [t for t in threads if display_name(t).casefold() == needle]
    if len(exact_name) == 1:
        return exact_name[0]
    matches = [
        t
        for t in threads
        if needle in display_name(t).casefold()
        or needle in t.title.casefold()
        or needle in t.preview.casefold()
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise PhantomError(f"No task matches {selector!r}. Use `list` to find its ID.")
    sample = "\n".join(f"  {t.id}  {display_name(t)}" for t in matches[:12])
    more = "\n  ..." if len(matches) > 12 else ""
    raise PhantomError(f"Selector {selector!r} is ambiguous:\n{sample}{more}\nUse the task ID.")


def canonical_basename(path: Path, thread_id: str) -> str | None:
    # Also recover names created by the first Prism-specific script, such as
    # repaired-rollout-...jsonl, by extracting the canonical suffix.
    index = path.name.find("rollout-")
    if index < 0:
        return None
    candidate = path.name[index:]
    match = CANONICAL_RE.fullmatch(candidate)
    if not match or match.group("thread_id") != thread_id:
        return None
    return candidate


def scan_tail(path: Path, offset: int, next_ordinal: int) -> tuple[list[Duplicate], int, int, dict | None]:
    expected = next_ordinal
    duplicates: list[Duplicate] = []
    valid = 0
    with path.open("rb") as stream:
        stream.seek(offset)
        while True:
            position = stream.tell()
            line = stream.readline()
            if not line:
                break
            try:
                record = json.loads(line)
            except Exception as exc:
                return duplicates, valid, expected, {
                    "byte_offset": position,
                    "expected": expected,
                    "actual": None,
                    "payload_type": None,
                    "error": f"invalid JSON: {exc}",
                }
            ordinal = record.get("ordinal")
            payload_type = (record.get("payload") or {}).get("type")
            if ordinal == expected:
                expected += 1
                valid += 1
            elif ordinal == expected - 1 and payload_type == "thread_settings_applied":
                duplicates.append(Duplicate(position, ordinal, payload_type))
            else:
                return duplicates, valid, expected, {
                    "byte_offset": position,
                    "expected": expected,
                    "actual": ordinal,
                    "payload_type": payload_type,
                    "error": "unsupported ordinal discontinuity",
                }
    return duplicates, valid, expected, None


def classify(thread: ThreadInfo, history: sqlite3.Connection) -> ScanResult:
    path = Path(thread.rollout_path) if thread.rollout_path else None
    if thread.history_mode != "paginated":
        return ScanResult("legacy", "task does not use paginated history")
    if path is None or not path.is_file():
        return ScanResult("missing-rollout", f"rollout not found: {thread.rollout_path}")

    size = path.stat().st_size
    canonical = canonical_basename(path, thread.id)
    name_ok = canonical == path.name
    projection = history.execute(
        "SELECT next_rollout_byte_offset, next_rollout_ordinal "
        "FROM thread_history_projection_state WHERE thread_id = ?",
        (thread.id,),
    ).fetchone()
    turns = history.execute(
        "SELECT count(*) FROM thread_turns WHERE thread_id = ?", (thread.id,)
    ).fetchone()[0]
    items = history.execute(
        "SELECT count(*) FROM thread_items WHERE thread_id = ?", (thread.id,)
    ).fetchone()[0]
    base = dict(
        file_size=size,
        turns=turns,
        items=items,
        canonical_name=canonical,
        canonical_filename=name_ok,
    )
    if canonical is None:
        return ScanResult("broken", "cannot derive a canonical rollout filename", **base)
    if projection is None:
        return ScanResult("no-projection", "paginated task has no projection cursor", **base)
    offset, next_ordinal = map(int, projection)
    common = dict(
        **base,
        projection_offset=offset,
        next_ordinal=next_ordinal,
        tail_bytes=size - offset,
    )
    if offset < 0 or offset > size:
        return ScanResult("broken", "projection offset is outside the rollout", **common)
    if turns == 0 or items == 0:
        return ScanResult("empty-projection", "projection cursor exists but turns/items are empty", **common)
    if offset == size:
        if not name_ok:
            return ScanResult("invalid-name", "history is complete but rollout basename is non-canonical", **common)
        return ScanResult("ok", "projection reaches end of rollout", **common)

    duplicates, valid, final_ordinal, mismatch = scan_tail(path, offset, next_ordinal)
    tail = dict(
        **common,
        duplicates=duplicates,
        valid_tail_records=valid,
        final_ordinal=final_ordinal,
        mismatch=mismatch,
    )
    if mismatch is not None:
        return ScanResult("broken", mismatch["error"], **tail)
    if duplicates:
        status = "phantom" if name_ok else "phantom+invalid-name"
        return ScanResult(status, "safe duplicate settings events block projection", **tail)
    if not name_ok:
        return ScanResult("invalid-name", "valid pending tail but rollout basename is non-canonical", **tail)
    return ScanResult("pending", "tail is ordinal-contiguous and should be projectable", **tail)


def format_time(epoch: int) -> str:
    return dt.datetime.fromtimestamp(epoch).astimezone().strftime("%Y-%m-%d %H:%M") if epoch else "-"


def human_bytes(value: int | None) -> str:
    if value is None:
        return "-"
    if value < 1024:
        return f"{value}B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f}K"
    return f"{value / (1024 * 1024):.1f}M"


def result_dict(thread: ThreadInfo, result: ScanResult) -> dict:
    data = asdict(result)
    data["repairable"] = result.repairable
    return {"thread": asdict(thread), "scan": data}


def command_list(args: argparse.Namespace) -> int:
    state_path, history_path = database_paths(args.codex_dir)
    threads = load_threads(state_path, include_archived=args.include_archived)
    rows: list[tuple[ThreadInfo, ScanResult]] = []
    with connect(history_path, readonly=True) as history:
        for thread in threads:
            result = classify(thread, history)
            if not args.all and result.status == "legacy":
                continue
            if args.problem_only and result.status in {f"ok", "legacy", "pending"}:
                continue
            rows.append((thread, result))
    if args.json:
        print(json.dumps([result_dict(t, r) for t, r in rows], indent=2))
        return 0

    print(f"{'STATUS':22} {'UPDATED':16} {'TURNS':>5} {'TAIL':>7} {'DUP':>3}  {'ID':36}  NAME")
    print("-" * 118)
    for thread, result in rows:
        name = display_name(thread)
        if len(name) > 52:
            name = name[:49] + "..."
        print(
            f"{result.status:22} {format_time(thread.updated_at):16} "
            f"{result.turns:5d} {human_bytes(result.tail_bytes):>7} "
            f"{len(result.duplicates):3d}  {thread.id}  {name}"
        )
    print(f"\n{len(rows)} task(s). Use: {Path(__file__).resolve()} check <ID-or-unique-name>")
    return 0


def command_check(args: argparse.Namespace) -> int:
    state_path, history_path = database_paths(args.codex_dir)
    thread = resolve_thread(state_path, args.chat)
    with connect(history_path, readonly=True) as history:
        result = classify(thread, history)
    if args.json:
        print(json.dumps(result_dict(thread, result), indent=2))
        return 0

    print(f"ID:                 {thread.id}")
    print(f"Name:               {display_name(thread)}")
    print(f"Status:             {result.status}")
    print(f"Detail:             {result.detail}")
    print(f"Updated:            {format_time(thread.updated_at)}")
    print(f"Archived:           {thread.archived}")
    print(f"History mode:       {thread.history_mode}")
    print(f"Rollout:            {thread.rollout_path or '-'}")
    print(f"Canonical filename: {result.canonical_filename}")
    print(f"Projection offset:  {result.projection_offset}")
    print(f"Rollout size:       {result.file_size}")
    print(f"Unprojected tail:   {result.tail_bytes} ({human_bytes(result.tail_bytes)})")
    print(f"Next ordinal:       {result.next_ordinal}")
    print(f"Projected rows:     turns={result.turns}, items={result.items}")
    print(f"Safe duplicates:    {len(result.duplicates)}")
    for duplicate in result.duplicates:
        print(f"  byte={duplicate.byte_offset} ordinal={duplicate.ordinal} type={duplicate.payload_type}")
    if result.mismatch:
        print(f"Unsupported issue:  {json.dumps(result.mismatch, ensure_ascii=False)}")
    print(f"Apply allowed:      {result.repairable}")
    return 0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fsync_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def sqlite_backup(source: Path, destination: Path) -> None:
    with connect(source, readonly=True) as src, connect(destination) as dst:
        src.backup(dst)
        integrity(dst, str(destination))


def write_active_copy(source: Path, destination: Path, result: ScanResult) -> None:
    duplicate_offsets = {item.byte_offset for item in result.duplicates}
    offset = result.projection_offset
    if offset is None:
        raise PhantomError("Internal error: no projection offset")
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with source.open("rb") as src, temporary.open("xb") as dst:
            remaining = offset
            while remaining:
                chunk = src.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise PhantomError("Rollout ended before its projection offset")
                dst.write(chunk)
                remaining -= len(chunk)
            while True:
                position = src.tell()
                line = src.readline()
                if not line:
                    break
                if position not in duplicate_offsets:
                    dst.write(line)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(temporary, destination)
        fsync_dir(destination.parent)
    finally:
        if temporary.exists():
            temporary.unlink()

    with source.open("rb") as original, destination.open("rb") as active:
        if original.read(offset) != active.read(offset):
            raise PhantomError("Validation failed: projected prefix changed")
    duplicates, _, _, mismatch = scan_tail(destination, offset, int(result.next_ordinal))
    if duplicates or mismatch:
        raise PhantomError("Validation failed: active rollout tail is not ordinal-contiguous")


def command_apply(args: argparse.Namespace) -> int:
    if not args.confirm_app_closed:
        raise PhantomError("Close Codex completely, then add --confirm-app-closed")
    state_path, history_path = database_paths(args.codex_dir)
    thread = resolve_thread(state_path, args.chat)
    with connect(history_path, readonly=True) as history:
        integrity(history, str(history_path))
        result = classify(thread, history)
    if not result.repairable:
        raise PhantomError(
            f"Refusing apply: task status is {result.status!r} ({result.detail}). "
            "Only phantom and invalid-name states are supported."
        )
    canonical_name = result.canonical_name
    if canonical_name is None:
        raise PhantomError("Cannot derive canonical rollout filename")
    source = Path(thread.rollout_path)

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = args.backup_root / f"codex-phantom-{thread.id}-{stamp}-{os.getpid()}"
    original_dir = backup_dir / "original"
    active_dir = backup_dir / "active"
    original_dir.mkdir(parents=True, mode=0o700)
    active_dir.mkdir()
    state_backup = backup_dir / "state_5.sqlite"
    history_backup = backup_dir / "thread_history_1.sqlite"
    rollout_backup = original_dir / canonical_name
    active_rollout = active_dir / canonical_name

    sqlite_backup(history_path, history_backup)
    sqlite_backup(state_path, state_backup)
    shutil.copy2(source, rollout_backup)
    fsync_file(rollout_backup)
    write_active_copy(source, active_rollout, result)

    hashes = {
        "source": sha256(source),
        "backup": sha256(rollout_backup),
        "active": sha256(active_rollout),
    }
    if hashes["source"] != hashes["backup"]:
        raise PhantomError("Rollout backup hash mismatch; state database was not changed")
    manifest = {
        "schema": 2,
        "thread": asdict(thread),
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "state_path": str(state_path),
        "history_path": str(history_path),
        "original_rollout_path": str(source),
        "active_rollout_path": str(active_rollout),
        "scan_before": asdict(result),
        "backups": {
            "state": str(state_backup),
            "history": str(history_backup),
            "rollout": str(rollout_backup),
        },
        "sha256": hashes,
    }
    manifest_path = backup_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    fsync_file(manifest_path)

    with connect(state_path) as state:
        integrity(state, str(state_path))
        state.execute("BEGIN IMMEDIATE")
        cursor = state.execute(
            "UPDATE threads SET rollout_path = ? WHERE id = ? AND rollout_path = ?",
            (str(active_rollout), thread.id, str(source)),
        )
        if cursor.rowcount != 1:
            state.rollback()
            raise PhantomError("Task changed concurrently; state database was not modified")
        state.commit()
        integrity(state, str(state_path))

    executable = Path(__file__).resolve()
    print("APPLY OK")
    print(f"Task:               {thread.id}  {display_name(thread)}")
    print(f"Previous status:    {result.status}")
    print(f"Duplicates removed: {len(result.duplicates)}")
    print(f"Backup directory:   {backup_dir}")
    print("Restart Codex and open the task. To roll back, close Codex and run:")
    print(f"  {executable} restore {backup_dir} --confirm-app-closed")
    return 0


def command_restore(args: argparse.Namespace) -> int:
    if not args.confirm_app_closed:
        raise PhantomError("Close Codex completely, then add --confirm-app-closed")
    backup_dir = args.backup_dir.resolve()
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.is_file():
        raise PhantomError(f"Missing manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != 2 or "thread" not in manifest:
        raise PhantomError("Manifest was not created by this general phantom-history tool")
    thread_id = manifest["thread"]["id"]
    state_path = Path(manifest["state_path"])
    history_path = Path(manifest["history_path"])
    history_backup = Path(manifest["backups"]["history"])
    rollout_backup = Path(manifest["backups"]["rollout"])
    for path in (state_path, history_path, history_backup, rollout_backup):
        if not path.is_file():
            raise PhantomError(f"Required restore file is missing: {path}")
    if sha256(rollout_backup) != manifest["sha256"]["backup"]:
        raise PhantomError("Rollout backup hash mismatch")
    with connect(history_backup, readonly=True) as saved:
        integrity(saved, str(history_backup))

    with connect(history_path) as db:
        db.execute("ATTACH DATABASE ? AS saved", (str(history_backup),))
        db.execute("ATTACH DATABASE ? AS state_db", (str(state_path),))
        try:
            db.execute("BEGIN IMMEDIATE")
            for table in HISTORY_TABLES:
                db.execute(f"DELETE FROM main.{table} WHERE thread_id = ?", (thread_id,))
                db.execute(
                    f"INSERT INTO main.{table} SELECT * FROM saved.{table} WHERE thread_id = ?",
                    (thread_id,),
                )
            cursor = db.execute(
                "UPDATE state_db.threads SET rollout_path = ? WHERE id = ?",
                (manifest["original_rollout_path"], thread_id),
            )
            if cursor.rowcount != 1:
                raise PhantomError("Task is absent from the live state database")
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.execute("DETACH DATABASE state_db")
            db.execute("DETACH DATABASE saved")
        integrity(db, str(history_path))

    print("RESTORE OK")
    print(f"Task restored:     {thread_id}  {manifest['thread']['name']}")
    print(f"Backup preserved:  {backup_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--codex-dir", type=Path, default=Path.home() / ".codex",
        help="Codex data directory (default: ~/.codex)",
    )
    parser.add_argument(
        "--backup-root", type=Path, default=Path.home() / "Documents" / "Codex",
        help="parent directory for apply backups",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    list_parser = sub.add_parser("list", help="list tasks and their projection status")
    list_parser.add_argument("--all", action="store_true", help="also show legacy tasks")
    list_parser.add_argument("--include-archived", action="store_true")
    list_parser.add_argument("--problem-only", action="store_true")
    list_parser.add_argument("--json", action="store_true")

    check_parser = sub.add_parser("check", help="inspect one task without modifying it")
    check_parser.add_argument("chat", help="task UUID, UUID prefix, or unique name substring")
    check_parser.add_argument("--json", action="store_true")

    apply_parser = sub.add_parser("apply", help="back up and repair one supported task")
    apply_parser.add_argument("chat", help="task UUID, UUID prefix, or unique name substring")
    apply_parser.add_argument("--confirm-app-closed", action="store_true")

    restore_parser = sub.add_parser("restore", help="restore one task from an apply backup")
    restore_parser.add_argument("backup_dir", type=Path)
    restore_parser.add_argument("--confirm-app-closed", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.codex_dir = args.codex_dir.resolve()
    args.backup_root = args.backup_root.resolve()
    try:
        if args.command == "list":
            return command_list(args)
        if args.command == "check":
            return command_check(args)
        if args.command == "apply":
            return command_apply(args)
        if args.command == "restore":
            return command_restore(args)
        raise AssertionError(args.command)
    except (PhantomError, sqlite3.Error, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
