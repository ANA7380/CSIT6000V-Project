#!/usr/bin/env bash
# One allocation: loopback-only Qwen, stock Agent, and SDK file worker.
set -euo pipefail
umask 077
export PS1="${PS1-}"
: "${TACC_WORKDIR:?Submit this package with tcloud submit}"
: "${TACC_USERDIR:?Submit this package with tcloud submit}"
: "${SLURM_JOB_ID:?Submit this package with tcloud submit}"
cd "$TACC_WORKDIR"
export STOCK_RESULT_DIR="$TACC_USERDIR/online-stock-research/$SLURM_JOB_ID"
mkdir -p "$STOCK_RESULT_DIR"
printf 'RESULT_DIR=%s\nHOST=%s\nWORKDIR=%s\n' "$STOCK_RESULT_DIR" "$(hostname)" "$TACC_WORKDIR"
printf 'SDK_BOOTSTRAP=%s\n' "${CONDA_PREFIX:-unset}"
source /mnt/home/public/course-envs/CSIT6000V/project/activate.sh
: "${QWEN_RUN_DIR:?Course activation did not prepare a runtime}"
cleanup_runtime() { rm -rf -- "$QWEN_RUN_DIR"; }
trap cleanup_runtime EXIT
# The course rootfs omits IANA timezone data. Reuse the host database in this
# allocation's private /tmp runtime; never install into the public Python env.
if [[ ! -d /usr/share/zoneinfo ]]; then
    echo 'Host IANA timezone database is required for exchange-calendar dates.' >&2
    exit 1
fi
cp -a /usr/share/zoneinfo "$QWEN_RUN_DIR/zoneinfo"
export PYTHONTZPATH="$QWEN_RUN_DIR/zoneinfo"
export QWEN_CACHE_HOME="$TACC_USERDIR/CSIT6000V-project-cache"
mkdir -p "$QWEN_CACHE_HOME"
cp package-manifest.json "$STOCK_RESULT_DIR/package-manifest.json"
stock_deploy_mode=$(/usr/bin/python3 -c 'import json; print(json.load(open("deployment.json"))["mode"])')
if [[ "$stock_deploy_mode" == diagnostic ]]; then
    qwen-python -u deploy/tacc/diagnose.py
    exit
fi
# The public launcher hardcodes 0,1; derive IDs from the allocation's visible GPUs.
# Refuse unexpected visibility rather than launch on unallocated GPUs.
nvidia-smi --query-gpu=index,uuid,memory.free,memory.total --format=csv | tee "$STOCK_RESULT_DIR/gpus.csv"
mapfile -t stock_visible_gpus < <(nvidia-smi --query-gpu=index --format=csv,noheader)
if [[ ${#stock_visible_gpus[@]} -ne 2 ]]; then
    echo 'Expected exactly two GPU devices visible in this allocation.' >&2
    exit 1
fi
export CUDA_VISIBLE_DEVICES="${stock_visible_gpus[0]},${stock_visible_gpus[1]}"
printf 'Runtime GPU selection: %s\n' "$CUDA_VISIBLE_DEVICES"
# Supervisor uses the system Python for process control. The Agent runs through
# the course runtime's Python, never through the SDK proxy's empty environment.
/usr/bin/python3 -u deploy/tacc/supervisor.py &
stock_supervisor_pid=$!
forward_stop() {
    kill -"$1" "$stock_supervisor_pid" 2>/dev/null || true
    wait "$stock_supervisor_pid" || true
    exit "$2"
}
trap 'forward_stop TERM 143' TERM
trap 'forward_stop INT 130' INT
wait "$stock_supervisor_pid"
