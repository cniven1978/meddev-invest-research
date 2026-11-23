#!/usr/bin/env bash
# 回归自测：验证 qa_gate 该拦的拦住、该放的放行。
# 不依赖任何真实 BP，可安全提交与公开运行。
#
# 用法： ./scripts/selftest.sh

set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

pass=0
fail=0
skip=0

expect() {
  local label="$1" want="$2" dir="$3" extra="${4:-}"
  if [[ ! -d "$dir" ]]; then
    echo "  [skip] $label（缺 $dir）"
    skip=$((skip + 1))
    return
  fi
  # shellcheck disable=SC2086
  python3 scripts/qa_gate.py --run "$dir" $extra >/tmp/qa-selftest.log 2>&1
  local got=$?
  if [[ "$got" == "$want" ]]; then
    echo "  [ok]   $label (exit=$got)"
    pass=$((pass + 1))
  else
    echo "  [FAIL] $label 期望 exit=$want 实际 exit=$got"
    sed 's/^/         /' /tmp/qa-selftest.log
    fail=$((fail + 1))
  fi
}

echo "qa_gate 回归"
expect "越界与失据样例应被阻断" 1 evals/qa-gate/case-blocked
expect "合规样例应通过" 0 evals/qa-gate/case-pass
expect "工具权限不足被写成无风险应被阻断" 1 evals/qa-gate/case-toolgap
expect "页码误报不得阻断（ERCP 45万例 / P0 / （P0））" 0 evals/qa-gate/case-pageedge
expect "页码区间越界应被阻断（第41–42页 / pp.45-48）" 1 evals/qa-gate/case-pageout
expect "页码词块三类误报不得告警（数字型/否定型/空格差异）" 0 evals/qa-gate/case-pageterm --check-page-content
expect "矛盾推进意见应被阻断（单一结论规则）" 1 evals/qa-gate/case-actionconflict
expect "否定断言标为已核实事实应被阻断（不依赖 limitations 自述）" 1 evals/qa-gate/case-absence
expect "斜杠分隔的证据ID不得误报" 0 evals/qa-gate/case-idslash
expect "引用与否定语境的禁用词不得阻断（公司称/未完成）" 0 evals/qa-gate/case-forbidden-cited
expect "报告自己下禁用断言应被阻断（据我们判断不构成豁免）" 1 evals/qa-gate/case-forbidden-assert

echo
echo "通过 ${pass}，失败 ${fail}，跳过 ${skip}"
[[ $fail -eq 0 ]] || exit 1
