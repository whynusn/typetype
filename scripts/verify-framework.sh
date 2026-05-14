#!/usr/bin/env bash
# verify-framework.sh - Docs Framework V2 完整性验证脚本
set -uo pipefail

PROJECT_ROOT="${1:-.}"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
errors=0; warnings=0; passed=0

is_framework_repo() { [[ -f "$PROJECT_ROOT/skills/apply/SKILL.md" ]] && [[ -d "$PROJECT_ROOT/template" ]]; }
pass() { echo -e "  ${GREEN}✅${NC} $1"; passed=$((passed + 1)); }
warn() { echo -e "  ${YELLOW}⚠️${NC} $1"; warnings=$((warnings + 1)); }
fail() { echo -e "  ${RED}❌${NC} $1"; errors=$((errors + 1)); }

echo "============================================="
echo " Docs Framework V2 - 完整性验证"
echo " 项目: $(cd "$PROJECT_ROOT" && pwd)"
echo "============================================="
echo ""

is_framework_repo && echo "  模式: 框架仓库" || echo "  模式: 已应用项目"
echo ""

# 阶段1: 文件完整性
echo "阶段 1：文件完整性检查"
RF=("README.md" "AGENTS.md" "CLAUDE.md")
if ! is_framework_repo; then RF+=("CHANGELOG.md" "docs/ARCHITECTURE.md" "docs/meta/README.md" "docs/reference/README.md" "docs/guides/README.md" "docs/examples/README.md"); fi
for f in "${RF[@]}"; do [[ -f "$PROJECT_ROOT/$f" ]] && pass "$f 存在" || fail "缺失: $f"; done

if is_framework_repo; then
  echo ""; echo "  模板产出:"
  TF=(template/README.md template/AGENTS.md template/CLAUDE.md template/CHANGELOG.md template/docs/ARCHITECTURE.md template/docs/meta/README.md template/docs/reference/README.md template/docs/guides/README.md template/docs/examples/README.md skills/apply/SKILL.md)
  for f in "${TF[@]}"; do [[ -f "$PROJECT_ROOT/$f" ]] && pass "template: $f" || fail "模板缺失: $f"; done
else
  [[ -d "$PROJECT_ROOT/skills" ]] && warn "发现 skills/ 目录" || pass "无 skills/ 目录"
fi
echo ""

# 阶段2: FILL标记
echo "阶段 2：FILL 标记检查"
fc=0
while IFS= read -r -d '' f; do
  [[ "$f" == *"docs/history"* || "$f" == *".git"* ]] && continue
  c=$(grep -c '<!-- FILL:' "$f" 2>/dev/null || true)
  [[ $c -gt 0 ]] && warn "${f#$PROJECT_ROOT/} 有 $c 个 FILL" && fc=$((fc + c))
done < <(find "$PROJECT_ROOT" -name '*.md' -not -path '*/.git/*' -print0)
[[ $fc -eq 0 ]] && pass "无 FILL 标记"
echo ""

# 阶段3: 内部链接
echo "阶段 3：内部链接"
bl=0; FA=("$PROJECT_ROOT" "-name" "*.md" "-not" "-path" "*/.git/*")
is_framework_repo && FA+=("-not" "-path" "*/template/*")
skipm=false; is_framework_repo && skipm=true
while IFS= read -r -d '' f; do
  $skipm && [[ "$f" == *"MIGRATION.md" ]] && continue
  while IFS= read -r link; do
    [[ "$link" == http* || "$link" == \#* ]] && continue
    t="${link%%#*}"; fp="$(dirname "$f")/$t"
    if [[ ! -z "$t" && ! -f "$fp" && ! -d "$fp" ]]; then warn "断链: ${f#$PROJECT_ROOT/} -> $t"; bl=$((bl+1)); fi
  done < <(grep -oP '\[([^\]]+)\]\(\K[^)]+' "$f" 2>/dev/null || true)
done < <(find "${FA[@]}" -print0)
[[ $bl -eq 0 ]] && pass "链接有效" || fail "$bl 个断链"
echo ""

# 阶段4: 框架一致性
echo "阶段 4：框架一致性"
MF="$PROJECT_ROOT/docs/meta/README.md"
[[ ! -f "$MF" ]] && MF="$PROJECT_ROOT/template/docs/meta/README.md"
if [[ -f "$MF" ]]; then
  m=$(cat "$MF")
  (echo "$m" | grep -q "内容契约" || echo "$m" | grep -q "文档类型定义") && echo "$m" | grep -q "分级复制" && pass "meta 规范完整" || fail "meta 缺少核心规范"
else
  fail "meta/README.md 不存在"
fi
AF="$PROJECT_ROOT/template/AGENTS.md"
is_framework_repo || AF="$PROJECT_ROOT/AGENTS.md"
[[ -f "$AF" ]] && cat "$AF" | grep -q "权威矩阵" && pass "AGENTS 含权威矩阵" || fail "AGENTS 缺少权威矩阵"
echo ""

# 阶段5: 文档状态标记
echo "阶段 5：文档状态标记"
sok=true
while IFS= read -r -d '' f; do
  [[ "$f" == *".git"* || "$f" == *"docs/history"* ]] && continue
  b=$(basename "$f")
  case "$b" in README.md|MIGRATION.md|CHANGELOG.md|LICENSE*) continue ;; esac
  grep -q '<!-- 状态:' "$f" 2>/dev/null || { warn "${f#$PROJECT_ROOT/} 缺状态标记"; sok=false; }
done < <(find "$PROJECT_ROOT" -name '*.md' -not -path '*/.git/*' -print0)
$sok && pass "状态标记齐全"
echo ""

echo "============================================="
echo -e "  通过: ${GREEN}${passed}${NC}  警告: ${YELLOW}${warnings}${NC}  错误: ${RED}${errors}${NC}"
echo "============================================="
[[ $errors -eq 0 ]] && echo -e "${GREEN}✅ 验证通过${NC}" && exit 0 || echo -e "${RED}❌ $errors 个问题${NC}" && exit 1