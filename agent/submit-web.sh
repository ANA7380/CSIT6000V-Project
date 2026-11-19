#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
mkdir "$stage/stock-chat"
cp -r data agent.py analysis_tools.py chat_agent.py tool_registry.py qwen_client.py \
    server-url.txt job.sh web_worker.py chat.html "$stage/stock-chat/"
cp web-tuxiv.conf "$stage/stock-chat/tuxiv.conf"
(cd "$stage/stock-chat" && tcloud submit)
