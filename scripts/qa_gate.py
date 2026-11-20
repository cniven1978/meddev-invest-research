#!/usr/bin/env python3
"""交付前 QA 门禁：把“人再读一遍”变成可重复的机器拦截。

拦截的是 references/evidence-policy.md 与 references/synthesis-validation.md
里那些“读起来都对、实际越界”的错。发现问题必须回改正文，不是附一份说明。

用法：
    python3 qa_gate.py --run outputs/<case_id> [--strict] [--check-page-content]

退出码：0 通过（可能有 warn）；1 阻断（有 error）；2 运行失败。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

CLAIM_STATUS = {"公司声称", "已核实事实", "测算或推断", "未披露或待核验"}
SUPPORT_STATUS = {"支持", "部分支持", "不支持", "无法核验"}
SOURCE_TYPES = {"监管/政府原始记录", "公司或申办者披露", "原始研究与专业评价", "二手研究", "无来源线索"}
ACTIONS = {"继续跟进", "补材料再评估", "暂停推进", "Pass"}

CLAIM_FIELDS = ["claim_id", "subject_scope_time", "statement", "claim_status",
                "evidence_ids", "support_status", "calculation_assumptions",
                "decision_impact", "next_verification"]
EVIDENCE_FIELDS = ["evidence_id", "source_type", "publisher", "title", "locator",
                   "published_or_effective_at", "accessed_at", "version_region",
                   "information_origin", "support_scope", "limitations", "origin_group"]

# 结论级禁用表述：出现即阻断。BP 原文的公司宣称在台账里，不进报告正文。
FORBIDDEN = [
    (r"投资总?分[：:为]?\s*\d", "出现投资总分"),
    (r"评分[：:为]?\s*\d+", "出现评分"),
    (r"灯号|红黄绿灯|绿灯|黄灯|红灯", "出现信号灯"),
    (r"已完成(尽职调查|尽调)|尽调已完成|完成尽调", "声称已完成尽调"),
    (r"已(全部|完整)?核实完毕", "声称全部核实完毕"),
    (r"行业第一|市场第一|绝对领先", "未经证据的排名断言"),
]

# 关键未知项：模板要求保留，不因章节省略而消失
KEY_UNKNOWNS = {
    "注册适用范围": r"注册|适用范围|适应症",
    "临床证据": r"临床",
    "收入与毛利": r"收入|毛利",
    "现金与资金需求": r"现金|资金需求|runway|跑道",
    "估值与条款": r"估值|条款",
}

# 工具侧未完成核验的表述。出现这些词，说明这一维度"没查到"是工具限制，
# 不是"没有"。把二者混为一谈是把工具故障当成事实结论。
TOOL_GAP_PATTERN = r"权限不足|未授权|无权限|需VIP|需SVIP|限流|超时|检索失败|接口不可用|未连接"

# 把工具限制误写成事实结论的表述
FALSE_NEGATIVE = [
    (r"未发现(任何)?(风险|诉讼|处罚|异常)", "未发现风险类断言"),
    (r"无(诉讼|被执行|行政处罚|经营异常|司法)记录", "无记录类断言"),
    (r"(司法|诉讼|合规)(风险)?(为无|不存在|清白)", "风险不成立类断言"),
]


class Gate:
    def __init__(self) -> None:
        self.findings: list[dict] = []

    def add(self, level: str, code: str, msg: str, where: str = "") -> None:
        self.findings.append({"level": level, "code": code, "message": msg, "where": where})

    @property
    def errors(self) -> list[dict]:
        return [f for f in self.findings if f["level"] == "error"]

    @property
    def warns(self) -> list[dict]:
        return [f for f in self.findings if f["level"] == "warn"]


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [row for row in csv.DictReader(fh)]


def check_headers(gate: Gate, rows: list[dict], fields: list[str], name: str) -> None:
    if not rows:
        gate.add("warn", "EMPTY_LEDGER", f"{name} 没有任何数据行", name)
        return
    missing = [f for f in fields if f not in rows[0]]
    if missing:
        gate.add("error", "MISSING_FIELD", f"{name} 缺字段：{', '.join(missing)}", name)


def check_claims(gate: Gate, claims: list[dict], evidence: dict[str, dict]) -> None:
    seen: set[str] = set()
    for row in claims:
        cid = (row.get("claim_id") or "").strip()
        where = cid or "(无ID)"
        if not cid:
            gate.add("error", "CLAIM_NO_ID", "主张缺 claim_id", where)
            continue
        if cid in seen:
            gate.add("error", "CLAIM_DUP_ID", f"claim_id 重复：{cid}", where)
        seen.add(cid)

        status = (row.get("claim_status") or "").strip()
        if status not in CLAIM_STATUS:
            gate.add("error", "CLAIM_STATUS_INVALID",
                     f"claim_status「{status}」不在四态之内（公司声称/已核实事实/测算或推断/未披露或待核验）", where)

        if not (row.get("statement") or "").strip():
            gate.add("error", "CLAIM_NO_STATEMENT", "主张陈述为空", where)
        if not (row.get("decision_impact") or "").strip():
            gate.add("error", "CLAIM_NO_IMPACT", "缺 decision_impact，无法判断这条主张为什么重要", where)

        support = (row.get("support_status") or "").strip()
        if support and support not in SUPPORT_STATUS:
            gate.add("error", "SUPPORT_INVALID",
                     f"support_status「{support}」不在 支持/部分支持/不支持/无法核验 之内", where)

        if status == "已核实事实" and support in {"不支持", "无法核验"}:
            gate.add("error", "STATUS_CONFLICT",
                     f"标为已核实事实却同时标为「{support}」，二者不可并存", where)

        # 否定型断言不能靠「已核实事实」成立：查无记录只能记未核验。
        # 这条判断必须独立于 evidence-ledger 的 limitations 自述——否则研究者
        # 只要不写「权限不足」，check_tool_gap_misuse 就降级为 warn，整道闸失守。
        for pattern, label in FALSE_NEGATIVE:
            if status == "已核实事实" and re.search(pattern, row.get("statement") or ""):
                gate.add("error", "ABSENCE_AS_VERIFIED",
                         f"「{label}」不能标为已核实事实：查无记录不等于无此事，"
                         f"只能记未披露或待核验，且不得依赖 limitations 自报工具缺口", where)
                break

        # 分隔符含斜杠与竖线：E-01/E-02、E-01|E-02 都是常见写法，
        # 漏掉会把合法引用判成「引用了不存在的证据」，逼研究者改格式迁就门禁。
        ids = [x.strip() for x in re.split(r"[;,，、\s/|｜+＋]+", row.get("evidence_ids") or "")
               if x.strip()]
        for eid in ids:
            if eid.upper() in {"NA", "N/A", "无", "-", "待核验"}:
                continue
            if eid not in evidence:
                gate.add("error", "EVIDENCE_UNKNOWN", f"引用了不存在的证据 {eid}", where)

        if status in {"已核实事实", "测算或推断"} and not ids:
            gate.add("error", "CLAIM_NO_EVIDENCE",
                     f"标为「{status}」却没有任何证据ID", where)

        if status == "已核实事实" and ids:
            groups = {evidence[i].get("origin_group", "") for i in ids if i in evidence}
            groups.discard("")
            if len(groups) == 1 and len(ids) > 1:
                gate.add("warn", "SAME_ORIGIN",
                         f"多条证据同属同源组「{next(iter(groups))}」，不构成交叉验证", where)

        if status in {"未披露或待核验", "测算或推断"} and not (row.get("next_verification") or "").strip():
            gate.add("warn", "NO_NEXT_STEP", "缺 next_verification，报告无法给出下一步动作", where)

        if status == "测算或推断" and not (row.get("calculation_assumptions") or "").strip():
            gate.add("error", "NO_ASSUMPTIONS", "测算/推断未记录输入与假设", where)


def check_evidence(gate: Gate, evidence: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    group_count: dict[str, int] = {}
    for row in evidence:
        eid = (row.get("evidence_id") or "").strip()
        where = eid or "(无ID)"
        if not eid:
            gate.add("error", "EVIDENCE_NO_ID", "来源缺 evidence_id", where)
            continue
        if eid in index:
            gate.add("error", "EVIDENCE_DUP_ID", f"evidence_id 重复：{eid}", where)
        index[eid] = row

        stype = (row.get("source_type") or "").strip()
        if stype not in SOURCE_TYPES:
            gate.add("error", "SOURCE_TYPE_INVALID", f"source_type「{stype}」不在五类之内", where)

        for field, label in (("publisher", "发布主体"), ("locator", "定位（URL/页码/记录ID）"),
                             ("accessed_at", "访问/读取日期")):
            if not (row.get(field) or "").strip():
                gate.add("error", f"EVIDENCE_NO_{field.upper()}", f"来源缺{label}", where)

        # 工具侧未完成：limitations 里写明了权限/限流/失败，这条来源不能支撑任何"无记录"结论
        limitations = row.get("limitations") or ""
        if re.search(TOOL_GAP_PATTERN, limitations):
            gate.add("warn", "TOOL_NOT_VERIFIED",
                     f"该来源标注了工具侧未完成（{limitations[:40]}），只能记“未核验”，不得写成“无此记录”",
                     where)

        group = (row.get("origin_group") or "").strip()
        if group:
            group_count[group] = group_count.get(group, 0) + 1

    for group, count in group_count.items():
        if count > 1:
            gate.add("warn", "ORIGIN_GROUP_REPEAT",
                     f"同源组「{group}」有 {count} 条来源，按规则只能算一次独立验证", group)
    return index


def extract_page_refs(text: str) -> set[int]:
    """抽取页码引用：只认明确写法，宁可漏报不可误报。

    门的目的是防「页码写错」，不是抓所有数字。误报会逼研究者删掉可复算的数字
    或改写正文来迁就检查，比漏报有害得多。历史误报三例，均由实跑记录证实：
    「ERCP 45 万例」被当成第 45 页、「P0/P1/P2」优先级被当成第 0/1/2 页、
    「（P0）」被当成第 0 页越界阻断。

    只接受三类明确写法，且区间两端都算：
      第45页 / 第45–50页      → 45、50
      p.12 / P.12 / pp.12-15  → 12、15
      （P12）/ (p12)          → 12
    不认「见 p 8」这种无点写法，也不认单独出现的 P0–P9：优先级标签与页码在
    字面上无法区分，认它就会误伤正文。漏检一份用「p 8」的稿子，代价小于逼人
    删掉一个可复算的数字。
    """
    refs: set[int] = set()

    def take(*groups: str) -> None:
        for value in groups:
            if value:
                page = int(value)
                if page >= 1:          # 第 0 页不存在，出现即标签而非页码
                    refs.add(page)

    # 第N页 / 第N–M页（连字符、短横、波浪、至）
    for match in re.finditer(r"第\s*(\d{1,3})\s*(?:[–\-~—至]\s*(\d{1,3})\s*)?[页頁]", text):
        take(*match.groups())

    # p.N / P.N / pp.N-M（必须有点，排除 ERCP 45 这类字母紧邻数字）
    for match in re.finditer(
            r"(?<![A-Za-z])[Pp]{1,2}\.\s*(\d{1,3})(?:\s*[–\-~—]\s*(\d{1,3}))?(?!\d)", text):
        take(*match.groups())

    # （PN）括号形式，全角半角均可
    for match in re.finditer(r"[（(]\s*[Pp]{1,2}\.?\s*(\d{1,3})\s*[)）]", text):
        take(*match.groups())

    return refs


def find_verdicts(text: str) -> list[str]:
    """找出报告里「下结论」的位置各自取了什么推进意见。

    全全文扫 ACTIONS 会把正文叙述误当结论，例如「本轮 pass 到下一阶段前需补齐材料」
    是过程描述，不是第二个结论。因此只认两类位置：
      1. 含「推进/结论/意见/建议/动作/评级」等判定语的行；
      2. 标题行（# 开头）里点明结论的。
    同一位置出现多个互斥词时，按出现顺序取第一个（模板首选项在前）。
    """
    verdicts: list[str] = []
    keys = ("推进", "结论", "意见", "建议", "动作", "评级", "判断", "定级")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not (stripped.startswith("#") or any(k in stripped for k in keys)):
            continue
        for action in ACTIONS:
            if action in stripped:
                if action not in verdicts:
                    verdicts.append(action)
                break
    return verdicts


def check_report(gate: Gate, text: str, page_count: int | None) -> None:
    if not text.strip():
        gate.add("error", "REPORT_EMPTY", "报告为空")
        return

    found_action = [a for a in ACTIONS if a in text]
    if not found_action:
        gate.add("error", "NO_ACTION",
                 f"报告没有给出推进意见，应取其一：{'/'.join(sorted(ACTIONS))}")
    else:
        # 推进意见必须唯一。矛盾结论比缺结论更危险：读者会各取所需。
        # 判定看「结论位」而非全文：只扫首屏推进动作行与各级标题里点明结论的地方，
        # 避免正文正常叙述（如「本轮 pass 到下一阶段前需补齐材料」）被误判为第二个结论。
        verdicts = find_verdicts(text)
        if len(verdicts) > 1:
            gate.add("error", "ACTION_CONFLICT",
                     f"报告在不同位置给出互斥结论（{'/'.join(verdicts)}），"
                     f"同一份报告只能有一个推进意见")

    for pattern, label in FORBIDDEN:
        for match in re.finditer(pattern, text):
            snippet = text[max(0, match.start() - 20): match.end() + 20].replace("\n", " ")
            gate.add("error", "FORBIDDEN_PHRASE", f"{label}：「...{snippet}...」")

    gaps = [name for name, pattern in KEY_UNKNOWNS.items() if not re.search(pattern, text)]
    for name in gaps:
        gate.add("warn", "KEY_UNKNOWN_MISSING",
                 f"报告未提及「{name}」，关键未知不因章节精简而消失；不适用时请写明原因")

    if page_count:
        bad = sorted(n for n in extract_page_refs(text) if n > page_count or n < 1)
        if bad:
            gate.add("error", "PAGE_OUT_OF_RANGE",
                     f"引用页码超出材料范围（共 {page_count} 页）：{bad}")

    if "未披露" not in text and "待核验" not in text:
        gate.add("warn", "NO_GAP_MARKED",
                 "报告未出现「未披露/待核验」，需确认是否真的没有缺口，还是把缺口写成了结论")


def check_tool_gap_misuse(gate: Gate, text: str, evidence: list[dict]) -> None:
    """工具没查到 ≠ 事实层面不存在。两边对不上时报错。"""
    has_tool_gap = any(re.search(TOOL_GAP_PATTERN, row.get("limitations") or "")
                       or re.search(TOOL_GAP_PATTERN, row.get("support_scope") or "")
                       for row in evidence)
    gaps_in_report = bool(re.search(TOOL_GAP_PATTERN, text))

    for pattern, label in FALSE_NEGATIVE:
        for match in re.finditer(pattern, text):
            snippet = text[max(0, match.start() - 25): match.end() + 25].replace("\n", " ")
            if has_tool_gap and not gaps_in_report:
                gate.add("error", "TOOL_GAP_AS_FACT",
                         f"{label}，但台账中存在工具侧未完成的维度，且报告未披露该限制："
                         f"「...{snippet}...」")
            else:
                gate.add("warn", "NEGATIVE_CLAIM",
                         f"{label}，请确认该维度已完整核验（非工具限制所致）：「...{snippet}...」")


# 否定型陈述天然不会与页面文字重合，对它们比对页码没有意义
ABSENCE_MARKERS = re.compile(r"未披露|未提及|未给|未提供|缺失|未说明|待核验|无记录|无法核验")


def check_page_content(gate: Gate, claims: list[dict], pages: list[dict]) -> None:
    """抽查：主张引用的页码上，是否真的出现主张里的关键词。只报 warn。

    这是启发式，误报会逼研究者改写主张实质，所以宁可少报。实跑记录显示三类
    结构性误报，都无法靠调阈值解决，因此在源头排除：
      1. 空格差异——页面上「成立于 2017 年」与主张「成立于2017年」是同一句，先双侧去空白；
      2. 数字为主的主张——「45万例×30%×85%×8000元」的中文三字块本来就不会出现在页面上；
      3. 否定型主张——「失访与置信区间均未披露」这类陈述，页面上不可能有对应文字。
    只在「有足够中文叙述、非否定型、且整句零重合」时才提示。
    """
    if not pages:
        return
    by_page = {p["page"]: re.sub(r"\s+", "", p.get("text", "")) for p in pages}
    for row in claims:
        locator = f"{row.get('evidence_ids', '')} {row.get('next_verification', '')}"
        nums = sorted(extract_page_refs(locator))
        if not nums:
            continue
        statement = re.sub(r"\s+", "", row.get("statement") or "")

        if ABSENCE_MARKERS.search(statement):
            continue                      # 否定型主张，跳过
        digits = sum(ch.isdigit() for ch in statement)
        if digits and digits >= len(statement) * 0.2:
            continue                      # 数字为主，中文块不足以比对

        grams = set(re.findall(r"[\u4e00-\u9fff]{4}", statement))
        if len(grams) < 3:
            continue                      # 中文叙述太少，比对无意义

        page_text = "".join(by_page.get(n, "") for n in nums)
        if not page_text:
            gate.add("warn", "PAGE_TEXT_EMPTY",
                     f"第 {nums} 页文本为空，引用该页的主张需回原页图像核对", row.get("claim_id", ""))
            continue
        if not any(g in page_text for g in grams):
            gate.add("warn", "PAGE_TERM_MISS",
                     f"第 {nums} 页未出现主张中的任何四字词，页码或转述可能有误；"
                     f"确为转述可忽略本提示", row.get("claim_id", ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="BP 初筛交付前 QA 门禁")
    ap.add_argument("--run", required=True, help="本次运行目录，例如 outputs/<case_id>")
    ap.add_argument("--report", default=None, help="报告文件名，默认自动找 report.md")
    ap.add_argument("--strict", action="store_true", help="把 warn 也当作阻断")
    ap.add_argument("--check-page-content", action="store_true",
                    help="额外抽查页码与主张关键词是否对得上")
    args = ap.parse_args()

    run = Path(args.run).expanduser().resolve()
    if not run.is_dir():
        print(f"[fail] 运行目录不存在：{run}", file=sys.stderr)
        return 2

    gate = Gate()
    ledger = run / "ledger"
    claims_path, evidence_path = ledger / "claim-ledger.csv", ledger / "evidence-ledger.csv"

    claims = read_csv(claims_path) if claims_path.exists() else []
    evidence_rows = read_csv(evidence_path) if evidence_path.exists() else []
    if not claims_path.exists():
        gate.add("error", "NO_CLAIM_LEDGER", "缺 ledger/claim-ledger.csv")
    if not evidence_path.exists():
        gate.add("error", "NO_EVIDENCE_LEDGER", "缺 ledger/evidence-ledger.csv")

    check_headers(gate, claims, CLAIM_FIELDS, "claim-ledger")
    check_headers(gate, evidence_rows, EVIDENCE_FIELDS, "evidence-ledger")
    evidence_index = check_evidence(gate, evidence_rows)
    check_claims(gate, claims, evidence_index)

    report_path = run / args.report if args.report else run / "report.md"
    text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    if not report_path.exists():
        gate.add("error", "NO_REPORT", f"找不到报告：{report_path.name}")

    manifest_path = run / "intake" / "source-manifest.json"
    page_count, pages = None, []
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        page_count = manifest.get("page_count")
        pages_path = run / "intake" / "bp-pages.json"
        if pages_path.exists():
            pages = json.loads(pages_path.read_text(encoding="utf-8"))
    else:
        gate.add("warn", "NO_MANIFEST", "缺 intake/source-manifest.json，无法核对页码范围")

    check_report(gate, text, page_count)
    check_tool_gap_misuse(gate, text, evidence_rows)
    if args.check_page_content:
        check_page_content(gate, claims, pages)

    blocked = bool(gate.errors) or (args.strict and bool(gate.warns))
    result = {
        "run": str(run),
        "report": report_path.name if report_path.exists() else None,
        "counts": {"claims": len(claims), "evidence": len(evidence_rows),
                   "errors": len(gate.errors), "warnings": len(gate.warns)},
        "verdict": "blocked" if blocked else "passed",
        "findings": gate.findings,
    }
    (run / "qa-report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'[blocked]' if blocked else '[passed]'} {run.name}")
    print(f"     主张 {len(claims)}　来源 {len(evidence_rows)}　"
          f"error {len(gate.errors)}　warn {len(gate.warns)}")
    for level, tag in (("error", "E"), ("warn", "W")):
        items = [f for f in gate.findings if f["level"] == level]
        for item in items:
            loc = f" @{item['where']}" if item["where"] else ""
            print(f"  {tag} {item['code']}: {item['message']}{loc}")
    if blocked:
        print("     >> 回改正文与台账后重跑；不要只附一份引用问题说明。")
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
