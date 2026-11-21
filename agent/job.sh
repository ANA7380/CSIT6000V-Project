#!/usr/bin/env bash
set -euo pipefail
umask 077
export PS1="${PS1-}"
: "${TACC_WORKDIR:?Submit with tcloud submit}"
: "${TACC_USERDIR:?Submit with tcloud submit}"
source /mnt/home/public/course-envs/CSIT6000V/project/activate.sh
trap 'rm -rf -- "$QWEN_RUN_DIR"' EXIT
cd "$TACC_WORKDIR"
mkdir -p "$TACC_USERDIR/ticker-metrics-results"
QWEN_BASE_URL=$(qwen-python qwen_client.py --check-url --base-url "$(cat server-url.txt)")
export QWEN_BASE_URL
service_host=${QWEN_BASE_URL#*://}
if [[ "$service_host" == \[* ]]; then
    service_host=${service_host#\[}
    service_host=${service_host%%\]*}
else
    service_host=${service_host%%[:/]*}
fi
export no_proxy="${no_proxy:+$no_proxy,}${service_host},127.0.0.1,localhost"
export NO_PROXY="$no_proxy"
if [[ ${1:-} == web ]]; then
    umask 077
    qwen-python -u web_worker.py
    exit
fi
qwen-python -u chat_agent.py --provider qwen --prompt-file question.txt --log "$TACC_USERDIR/ticker-metrics-results/job-${SLURM_JOB_ID:-manual}.jsonl"
