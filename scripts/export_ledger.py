#!/usr/bin/env python3
"""把两张 CSV 台账导出成可筛选的 xlsx 交付件。

CSV 是工作格式（便于 diff 与脚本校验），xlsx 是交付格式（便于评审与筛选）。

用法：
    python3 export_ledger.py --run outputs/<case_id>
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="E1F5EE")
HEADER_FONT = Font(bold=True, size=11)
WRAP = Alignment(wrap_text=True, vertical="top")

WIDTHS = {
    "claim_id": 12, "subject_scope_time": 22, "statement": 52, "claim_status": 14,
    "evidence_ids": 16, "support_status": 12, "calculation_assumptions": 34,
    "decision_impact": 34, "next_verification": 34,
    "evidence_id": 12, "source_type": 20, "publisher": 24, "title": 40,
    "locator": 44, "published_or_effective_at": 16, "accessed_at": 14,
    "version_region": 16, "information_origin": 20, "support_scope": 34,
    "limitations": 30, "origin_group": 16,
}


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def write_sheet(wb: Workbook, title: str, fields: list[str], rows: list[dict]) -> None:
    ws = wb.create_sheet(title)
    ws.append(fields)
    for cell in ws[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(vertical="center")
    for row in rows:
        ws.append([row.get(f, "") for f in fields])
    for idx, field in enumerate(fields, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = WIDTHS.get(field, 18)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = WRAP
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def main() -> int:
    ap = argparse.ArgumentParser(description="台账 CSV → xlsx")
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    run = Path(args.run).expanduser().resolve()
    ledger = run / "ledger"
    claim_path, evid_path = ledger / "claim-ledger.csv", ledger / "evidence-ledger.csv"
    if not claim_path.exists() or not evid_path.exists():
        print("[fail] ledger/ 下缺 claim-ledger.csv 或 evidence-ledger.csv", file=sys.stderr)
        return 2

    claim_fields, claims = read_csv(claim_path)
    evid_fields, evidences = read_csv(evid_path)

    wb = Workbook()
    wb.remove(wb.active)
    write_sheet(wb, "主张表", claim_fields, claims)
    write_sheet(wb, "来源表", evid_fields, evidences)

    ws = wb.create_sheet("核验进度")
    ws.append(["优先级", "主张ID", "待核验事项", "所需材料", "状态"])
    for cell in ws[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    for claim in claims:
        if (claim.get("claim_status") or "").strip() in {"未披露或待核验", "测算或推断"}:
            ws.append(["", claim.get("claim_id", ""), claim.get("next_verification", ""),
                       claim.get("decision_impact", ""), "待办"])
    for idx, width in enumerate([10, 14, 46, 40, 10], start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.freeze_panes = "A2"

    target = Path(args.out) if args.out else run / "deliverables" / f"{run.name}-证据台账.xlsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    wb.save(target)
    print(f"[ok] {target}")
    print(f"     主张 {len(claims)} 条　来源 {len(evidences)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
