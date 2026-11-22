#!/usr/bin/env bash
# Copy the agent sources and data next to the evaluation code so one `tcloud submit`
# uploads everything the batch job needs. Rerun after changing anything in ../agent.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p agent_src/data
for f in agent.py analysis_tools.py chat_agent.py tool_registry.py evidence.py session_store.py qwen_client.py deepseek_client.py; do
    cp -f "../agent/$f" agent_src/
done
cp -f ../agent/data/*.csv agent_src/data/
echo "Bundled agent sources into $(pwd)/agent_src"
