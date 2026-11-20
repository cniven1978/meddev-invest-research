#!/usr/bin/env python3
"""批量受理：扫收件目录 → 去重 → 建运行目录 → 生成待跑队列。

本脚本只做“把材料摆好、把活排好”，不起子 Agent、不写判断。
逐个跑由宿主执行（见 workflows/bp-screening.md 的批量模式）。

用法：
    python3 batch.py --inbox ~/Desktop/项目-BP资料 --out outputs
    python3 batch.py --inbox ... --out ... --limit 5 --dry-run
    python3 batch.py --out outputs --status            # 只看队列现状

产出：
    <out>/_state/processed.json     已受理清单（按 sha256 去重）
    <out>/_state/queue.json         待跑队列
    <out>/_state/batch-summary.csv  横向汇总骨架（每份一行，待填结论）
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

SUFFIXES = {".pdf", ".pptx", ".docx"}
SKIP_PATTERNS = [r"^~\$", r"^\.", r"^~"]
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "assets" / "templates"

SUMMARY_FIELDS = [
    "case_id", "项目名称", "材料版本日期", "产品类型", "阶段", "推进意见",
    "最关键正向证据", "决定性缺口", "已核实问题数", "待核验数", "受理日", "状态",
]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def case_id_for(path: Path) -> str:
    stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", path.stem).strip("-")
    return f"{stem}-{date.today().isoformat()}"


def should_skip(path: Path) -> bool:
    return any(re.search(p, path.name) for p in SKIP_PATTERNS) or path.suffix.lower() not in SUFFIXES


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def scan(inbox: Path, recursive: bool) -> list[Path]:
    it = inbox.rglob("*") if recursive else inbox.iterdir()
    return sorted(p for p in it if p.is_file() and not should_skip(p))


def prepare_run(out: Path, src: Path, cid: str, run_intake: bool) -> dict:
    run = out / cid
    (run / "intake").mkdir(parents=True, exist_ok=True)
    (run / "ledger").mkdir(parents=True, exist_ok=True)
    (run / "deliverables").mkdir(parents=True, exist_ok=True)

    for name, target in (("claim-ledger.csv", "claim-ledger.csv"),
                         ("evidence-ledger.csv", "evidence-ledger.csv")):
        dst = run / "ledger" / target
        if not dst.exists() and (TEMPLATE_DIR / name).exists():
            shutil.copyfile(TEMPLATE_DIR / name, dst)

    intake_ok = False
    if run_intake:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import intake as intake_mod  # noqa: E402

        argv = ["intake.py", str(src), "--out", str(run), "--case-id", "intake"]
        old, sys.argv = sys.argv, argv
        try:
            intake_ok = intake_mod.main() == 0
        finally:
            sys.argv = old
    return {"case_id": cid, "run_dir": str(run), "intake_ok": intake_ok}


def write_summary(out: Path, state: dict) -> Path:
    path = out / "_state" / "batch-summary.csv"
    rows = []
    for sha, rec in state.items():
        rows.append({
            "case_id": rec["case_id"], "项目名称": rec.get("项目名称", ""),
            "材料版本日期": rec.get("材料版本日期", ""), "产品类型": rec.get("产品类型", ""),
            "阶段": rec.get("阶段", ""), "推进意见": rec.get("推进意见", ""),
            "最关键正向证据": rec.get("最关键正向证据", ""), "决定性缺口": rec.get("决定性缺口", ""),
            "已核实问题数": rec.get("已核实问题数", ""), "待核验数": rec.get("待核验数", ""),
            "受理日": rec.get("受理日", ""), "状态": rec.get("status", ""),
        })
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="BP 批量受理与队列生成")
    ap.add_argument("--inbox", help="收件目录")
    ap.add_argument("--out", default="outputs", help="输出根目录，默认 ./outputs")
    ap.add_argument("--limit", type=int, default=0, help="本次最多受理几份，0 为不限")
    ap.add_argument("--recursive", action="store_true", help="递归扫描子目录")
    ap.add_argument("--dry-run", action="store_true", help="只列清单不落盘")
    ap.add_argument("--no-intake", action="store_true", help="只建目录，不跑受理登记")
    ap.add_argument("--status", action="store_true", help="只打印当前队列状态")
    args = ap.parse_args()

    out = Path(args.out).expanduser().resolve()
    state_dir = out / "_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path, queue_path = state_dir / "processed.json", state_dir / "queue.json"
    state = load_json(state_path, {})

    if args.status:
        queue = load_json(queue_path, [])
        print(f"已受理 {len(state)} 份，待跑 {len(queue)} 份")
        for item in queue:
            print(f"  - {item['case_id']}  ({item['source_name']})")
        return 0

    if not args.inbox:
        print("[fail] 需要 --inbox 或 --status", file=sys.stderr)
        return 2
    inbox = Path(args.inbox).expanduser().resolve()
    if not inbox.is_dir():
        print(f"[fail] 收件目录不存在：{inbox}", file=sys.stderr)
        return 2

    candidates = scan(inbox, args.recursive)
    fresh, skipped = [], 0
    for path in candidates:
        digest = sha256_of(path)
        if digest in state:
            skipped += 1
            continue
        fresh.append((path, digest))
    if args.limit:
        fresh = fresh[: args.limit]

    print(f"扫描 {len(candidates)} 个文件：新 {len(fresh)}，已受理跳过 {skipped}")
    if args.dry_run:
        for path, _ in fresh:
            print(f"  + {path.name}")
        return 0

    queue = load_json(queue_path, [])
    queued_ids = {item["case_id"] for item in queue}
    for path, digest in fresh:
        cid = case_id_for(path)
        while cid in queued_ids or any(r["case_id"] == cid for r in state.values()):
            cid = f"{cid}-b"
        result = prepare_run(out, path, cid, run_intake=not args.no_intake)
        state[digest] = {
            "case_id": cid, "source_path": str(path), "source_name": path.name,
            "sha256": digest, "受理日": date.today().isoformat(),
            "status": "intake_done" if result["intake_ok"] else "intake_failed",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        queue.append({"case_id": cid, "run_dir": result["run_dir"],
                      "source_name": path.name, "source_path": str(path),
                      "queued_at": date.today().isoformat(), "status": "pending"})
        queued_ids.add(cid)
        flag = "ok" if result["intake_ok"] else "FAIL"
        print(f"  [{flag}] {cid}")

    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = write_summary(out, state)
    print(f"\n队列 {len(queue)} 份 → {queue_path}")
    print(f"汇总骨架 → {summary}")
    print("下一步：按 workflows/bp-screening.md 的批量模式，逐个 case 起独立上下文执行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
