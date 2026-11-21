#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ${1:-} != --external-model ]]; then
    # Default to the allocation-local Qwen endpoint from the supplied fix.
    exec python3 ../scripts/tacc.py submit --mode web "$@"
fi
shift
if [[ $# -ne 0 ]]; then
    echo 'The legacy --external-model mode accepts no further arguments.' >&2
    exit 2
fi
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
mkdir "$stage/stock-chat"
cp -r data agent.py analysis_tools.py chat_agent.py tool_registry.py qwen_client.py \
    server-url.txt job.sh web_worker.py session_store.py evidence.py chat.html "$stage/stock-chat/"
cp web-tuxiv.conf "$stage/stock-chat/tuxiv.conf"
(cd "$stage/stock-chat" && "${TCLOUD_BIN:-tcloud}" submit)
