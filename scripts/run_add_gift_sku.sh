#!/usr/bin/env bash
# OpenClaw / cron 定时执行：管易待审核订单自动加赠品
#
# 用法（OpenClaw 任务命令示例）:
#   /home/gem/workspace/agent/workspace/guanyi/scripts/run_add_gift_sku.sh
#
# 可通过环境变量覆盖项目目录:
#   GUANYI_PROJECT_DIR=/path/to/guanyi ./scripts/run_add_gift_sku.sh

set -euo pipefail

PROJECT_DIR="${GUANYI_PROJECT_DIR:-/home/gem/workspace/agent/workspace/guanyi}"
cd "$PROJECT_DIR"

mkdir -p logs
LOCK_FILE="${GUANYI_LOCK_FILE:-$PROJECT_DIR/.run_add_gift_sku.lock}"
LOG_FILE="${GUANYI_LOG_FILE:-$PROJECT_DIR/logs/cron.log}"

# 防止上一轮未结束又启动（与 cron 间隔重叠时）
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "$(date '+%F %T') [skip] 上一轮仍在运行，跳过本次" >>"$LOG_FILE"
  exit 0
fi

# lark-cli 常在用户 PATH 外；按需补充
export PATH="${PATH:-}:/usr/local/bin:${HOME:-/home/gem}/.local/bin:${HOME:-/home/gem}/.npm-global/bin"

_ensure_venv() {
  if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    PYTHON="$PROJECT_DIR/.venv/bin/python"
    return 0
  fi

  local py_create=""
  if command -v python3 >/dev/null 2>&1; then
    py_create="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    py_create="$(command -v python)"
  else
    echo "[error] 未找到 python3，无法创建虚拟环境"
    return 1
  fi

  echo "[venv] 未检测到 .venv，正在创建 ($py_create -m venv .venv)"
  "$py_create" -m venv "$PROJECT_DIR/.venv"
  echo "[venv] 安装依赖: requirements.txt"
  "$PROJECT_DIR/.venv/bin/pip" install -q -r "$PROJECT_DIR/requirements.txt"
  PYTHON="$PROJECT_DIR/.venv/bin/python"
  echo "[venv] 就绪: $PYTHON"
}

{
  echo "======== $(date '+%F %T') ========"
  echo "dir=$PROJECT_DIR"
  _ensure_venv || exit 1
  echo "python=$PYTHON"
  "$PYTHON" add_gift_sku.py
  ec=$?
  echo "exit_code=$ec"
  exit "$ec"
} >>"$LOG_FILE" 2>&1
