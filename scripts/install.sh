#!/usr/bin/env bash
# 把本仓库同步到任意 skills-compatible runtime 的技能目录。
#
# 单一来源是本仓库（可 git 版本化）；被安装的目录是部署副本。
# 改动永远改仓库，然后重跑本脚本。不要直接改副本。
#
# 用法：
#   ./scripts/install.sh                 # 自动探测本机已存在的 runtime 目录
#   ./scripts/install.sh --target claude # 装到指定 runtime
#   ./scripts/install.sh --dir /path     # 装到任意路径
#   ./scripts/install.sh --dry-run       # 只看会做什么
#
# 可用 --target：workbuddy dsh agents claude codex cursor gemini
# 探测顺序（命中第一个即用）：workbuddy → dsh → claude → codex → cursor → gemini → agents

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_NAME="meddev-invest-research"
DRY=0
TARGET=""
EXPLICIT_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY=1; shift ;;
    --target) TARGET="${2:-}"; shift 2 ;;
    --dir) EXPLICIT_DIR="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数：$1（用 --help 看用法）" >&2; exit 2 ;;
  esac
done

# 各 runtime 的技能根目录，均可用对应环境变量覆盖
root_for() {
  case "$1" in
    workbuddy) echo "${WORKBUDDY_SKILLS_DIR:-$HOME/.workbuddy/skills}" ;;
    dsh)       echo "${DSH_HOME:-$HOME/.dsh}/skills" ;;
    agents)    echo "${DSH_AGENTS_HOME:-$HOME/.agents}/skills" ;;
    claude)    echo "${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}" ;;
    codex)     echo "${CODEX_SKILLS_DIR:-$HOME/.codex/skills}" ;;
    cursor)    echo "${CURSOR_SKILLS_DIR:-$HOME/.cursor/skills}" ;;
    gemini)    echo "${GEMINI_SKILLS_DIR:-$HOME/.gemini/skills}" ;;
    *) return 1 ;;
  esac
}

if [[ -n "$EXPLICIT_DIR" ]]; then
  ROOT="$EXPLICIT_DIR"; PICKED="自定义路径"
elif [[ -n "$TARGET" ]]; then
  ROOT="$(root_for "$TARGET")" || { echo "[fail] 未知 runtime：$TARGET" >&2; exit 2; }
  PICKED="$TARGET"
elif [[ -n "${SKILLS_DIR:-}" ]]; then
  ROOT="$SKILLS_DIR"; PICKED="SKILLS_DIR 环境变量"   # 通用变量，便于 CI 与自定义部署覆盖
else
  PICKED=""
  for candidate in workbuddy dsh claude codex cursor gemini agents; do
    dir="$(root_for "$candidate")"
    if [[ -d "$(dirname "$dir")" ]]; then ROOT="$dir"; PICKED="$candidate"; break; fi
  done
  if [[ -z "$PICKED" ]]; then
    echo "[fail] 没找到已安装的 runtime 目录。用 --target 或 --dir 指定，例如：" >&2
    echo "       ./scripts/install.sh --target claude" >&2
    echo "       ./scripts/install.sh --dir ~/my-agent/skills" >&2
    exit 2
  fi
fi

DEST="$ROOT/$SKILL_NAME"

echo "源：$REPO"
echo "目标：$DEST"
echo "运行环境：$PICKED"
echo

RSYNC_FLAGS=(-a --delete
  --exclude '.git' --exclude '__pycache__' --exclude '*.pyc'
  --exclude 'outputs' --exclude 'tmp' --exclude 'results.tsv')

if [[ $DRY -eq 1 ]]; then
  mkdir -p "$DEST"
  rsync "${RSYNC_FLAGS[@]}" -n "$REPO/" "$DEST/"
  echo "（dry-run，未写入）"
  exit 0
fi

mkdir -p "$DEST"
rsync "${RSYNC_FLAGS[@]}" "$REPO/" "$DEST/"
chmod +x "$DEST"/scripts/*.py "$DEST"/scripts/*.sh 2>/dev/null || true

# 安装后自检：frontmatter 可解析、name 合规、脚本可编译
python3 - "$DEST" "$SKILL_NAME" <<'PY'
import py_compile, pathlib, re, sys
dest, expected = pathlib.Path(sys.argv[1]), sys.argv[2]
skill = dest / "SKILL.md"
if not skill.exists():
    sys.exit(f"[fail] 未找到 {skill}")
text = skill.read_text(encoding="utf-8")
if not text.startswith("---"):
    sys.exit("[fail] SKILL.md 缺 YAML frontmatter")
front = text.split("---")[1]
name = re.search(r"^name:\s*(\S+)", front, re.M)
desc = re.search(r"^description:\s*(.+)$", front, re.M)
if not name or not desc:
    sys.exit("[fail] frontmatter 缺 name 或 description")
if name.group(1) != expected:
    # 各 runtime 只校验 name 是 kebab-case，并不要求与目录同名；这是本仓库自己的约定，
    # 保证重装后工具名与目录一致、便于排查，不是协议要求。
    sys.exit(f"[fail] name「{name.group(1)}」与目录名「{expected}」不一致（本仓库约定两者一致）")
if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name.group(1)):
    sys.exit(f"[fail] name「{name.group(1)}」不是 kebab-case")
if len(desc.group(1)) > 500:
    print(f"[warn] description {len(desc.group(1))} 字符，超过部分 runtime 的目录上限 500")
for script in sorted((dest / "scripts").glob("*.py")):
    try:
        py_compile.compile(str(script), doraise=True)
    except py_compile.PyCompileError as exc:
        sys.exit(f"[fail] {script.name} 语法错误：{exc}")
print(f"[ok] frontmatter 合规：name={name.group(1)}，description {len(desc.group(1))} 字符")
print("[ok] scripts/*.py 语法检查通过")
PY

echo
echo "已同步到 ${PICKED}。依赖：python3 + pymupdf + openpyxl + Pillow"
echo "  python3 -m pip install pymupdf openpyxl pillow"
echo
echo "验证：cd \"$DEST\" && ./scripts/selftest.sh"
