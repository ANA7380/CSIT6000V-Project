#!/usr/bin/env bash
# TACC batch entry point: run the evaluation set against the course Qwen service.
# Prepare with `bash bundle.sh`, set server-url.txt, then `tcloud submit` from this folder.
set -euo pipefail
: "${TACC_WORKDIR:?Submit with tcloud submit}"
: "${TACC_USERDIR:?Submit with tcloud submit}"
source /mnt/home/public/course-envs/CSIT6000V/project/activate.sh
cd "$TACC_WORKDIR"
test -f agent_src/agent.py || { echo 'agent_src/ is missing: run "bash bundle.sh" before tcloud submit.' >&2; exit 1; }
QWEN_BASE_URL=$(qwen-python agent_src/qwen_client.py --check-url --base-url "$(cat server-url.txt)")
export QWEN_BASE_URL
# Course service traffic is internal; bypass inherited HTTP proxy settings.
service_host=${QWEN_BASE_URL#*://}
if [[ "$service_host" == \[* ]]; then
    service_host=${service_host#\[}
    service_host=${service_host%%\]*}
else
    service_host=${service_host%%[:/]*}
fi
export no_proxy="${no_proxy:+$no_proxy,}${service_host},127.0.0.1,localhost"
export NO_PROXY="$no_proxy"
OUT="$TACC_USERDIR/stock-eval-results"
mkdir -p "$OUT"
# One "<system> <context>" pair per line in systems.txt; finished cases are skipped on resubmission.
while read -r system context; do
    [[ -z "${system:-}" || "$system" == \#* ]] && continue
    echo "=== $system (context: $context) ==="
    qwen-python -u run_eval.py --system "$system" --provider qwen --context "$context" --out-dir "$OUT"
done < systems.txt
echo "RESULT_DIR=stock-eval-results"
