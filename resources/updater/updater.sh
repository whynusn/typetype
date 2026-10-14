#!/usr/bin/env bash
# typetype 平台更新器（Linux / macOS，ADR-014 决策 5）
#
# 用法: updater.sh <install_dir> <stage_dir>
#   install_dir  当前安装目录（含旧版可执行文件与依赖）
#   stage_dir    已下载并解压好的新版目录（临时）
#
# 流程: 备份旧目录 -> 新版替换 -> 删除备份 -> 重启应用 -> 退出
# 幂等/失败保留: 任一步失败即中止，旧目录以 .bak 保留（脚本自身不删除时用户可手动恢复）
#
# 注意: 本脚本由应用 detach 调用（后台进程），应用自身退出后执行替换。
#       期间请勿手动关闭；替换是原子目录切换（rename），中途断电只会留下 .bak。

set -euo pipefail

INSTALL_DIR="${1:-}"
STAGE_DIR="${2:-}"
BACKUP_DIR="${INSTALL_DIR}.bak"

if [ -z "$INSTALL_DIR" ] || [ -z "$STAGE_DIR" ]; then
  echo "usage: $0 <install_dir> <stage_dir>" >&2
  exit 2
fi
if [ ! -d "$STAGE_DIR" ]; then
  echo "暂存目录不存在: $STAGE_DIR" >&2
  exit 1
fi
if [ ! -d "$INSTALL_DIR" ]; then
  echo "安装目录不存在: $INSTALL_DIR" >&2
  exit 1
fi

# macOS 产物为 .app 包整体替换（Nuitka 当前输出为 main.app）。
if [ "$(uname -s)" = "Darwin" ]; then
  APP_DIR=""
  for candidate in "$STAGE_DIR"/*.app; do
    if [ -d "$candidate" ]; then
      APP_DIR="$candidate"
      break
    fi
  done
  if [ -n "$APP_DIR" ]; then
    STAGE_DIR="$APP_DIR"
  fi
fi

# 1) 备份旧目录（同名 .bak；若已有备份先移除旧备份）
rm -rf "$BACKUP_DIR"
if ! mv "$INSTALL_DIR" "$BACKUP_DIR"; then
  echo "备份旧目录失败: $INSTALL_DIR -> $BACKUP_DIR" >&2
  exit 1
fi

# 2) 新版替换到安装目录（mv 优先；跨文件系统时 cp -r 兜底）
if ! mv "$STAGE_DIR" "$INSTALL_DIR" 2>/dev/null; then
  if ! cp -r "$STAGE_DIR" "$INSTALL_DIR"; then
    # 替换失败：回滚旧目录，尽力恢复原状
    mv "$BACKUP_DIR" "$INSTALL_DIR" 2>/dev/null
    echo "替换失败，已回滚旧目录" >&2
    exit 1
  fi
fi

# 3) 删除备份
rm -rf "$BACKUP_DIR"

# 4) 重启应用（Nuitka 入口名是 main.py，因此 standalone 产物通常是 main；
#    同时兼容历史/重命名后的 typetype）。
RESTART_BIN=""
if [ -d "$INSTALL_DIR/Contents/MacOS" ]; then
  for candidate in \
    "$INSTALL_DIR/Contents/MacOS/typetype" \
    "$INSTALL_DIR/Contents/MacOS/main"; do
    if [ -x "$candidate" ]; then
      RESTART_BIN="$candidate"
      break
    fi
  done
else
  for candidate in \
    "$INSTALL_DIR/typetype" \
    "$INSTALL_DIR/main"; do
    if [ -x "$candidate" ]; then
      RESTART_BIN="$candidate"
      break
    fi
  done
fi
if [ -n "${RESTART_BIN:-}" ] && [ -x "$RESTART_BIN" ]; then
  nohup "$RESTART_BIN" >/dev/null 2>&1 &
  disown
else
  echo "未找到可执行文件，请手动启动 $INSTALL_DIR" >&2
fi

exit 0
