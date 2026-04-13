#!/bin/bash
# Hermes Agent Capability Test Runner
# Run from the hermes-agent directory:
#   chmod +x run_tests.sh && ./run_tests.sh
#
# Telemetry goes to Honeycomb automatically (configured in cli-config.yaml)

set -euo pipefail
cd "$(dirname "$0")"

# macOS doesn't have `timeout` — use perl fallback
if ! command -v timeout &>/dev/null; then
    timeout() { perl -e 'alarm shift; exec @ARGV' "$@"; }
fi

# Activate venv if present
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

# Load env
set -a
source .env
set +a

echo "======================================================"
echo "  HERMES AGENT CAPABILITY TEST SUITE"
echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "======================================================"
echo ""

PASS=0
FAIL=0
WARN=0
RESULTS=""

run_test() {
    local category="$1"
    local name="$2"
    local prompt="$3"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "TEST: [$category] $name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    local start=$(date +%s)

    # Run agent non-interactively with timeout
    local output
    if output=$(timeout 120 python3 -c "
import os, sys, json
from dotenv import load_dotenv
load_dotenv('.env')
from run_agent import AIAgent

agent = AIAgent(
    base_url='https://api.z.ai/api/coding/paas/v4',
    model='glm-4.7',
    api_key=os.environ.get('GLM_API_KEY'),
)

result = agent.run_conversation('''$prompt''')

# run_conversation() returns a dict with keys: final_response, messages, api_calls, completed
if isinstance(result, dict):
    text = result.get('final_response', '') or result.get('content', '') or result.get('text', '') or ''
    messages = result.get('messages', [])
elif isinstance(result, str):
    text = result
    messages = []
else:
    text = str(result)
    messages = []

# Extract tool calls from the returned messages list (not agent.messages)
tools_used = []
for msg in messages:
    if isinstance(msg, dict) and msg.get('role') == 'assistant':
        tool_calls = msg.get('tool_calls', [])
        if tool_calls:
            for tc in tool_calls:
                fn = tc.get('function', {}) if isinstance(tc, dict) else {}
                tools_used.append(fn.get('name', 'unknown'))

# Also check if agent has _session_messages as fallback
if not tools_used and hasattr(agent, '_session_messages'):
    for msg in agent._session_messages:
        if isinstance(msg, dict) and msg.get('role') == 'assistant':
            tool_calls = msg.get('tool_calls', [])
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get('function', {}) if isinstance(tc, dict) else {}
                    tools_used.append(fn.get('name', 'unknown'))

print('TOOLS_USED:' + ','.join(tools_used))
print('RESPONSE_START')
print(str(text)[:500])
print('RESPONSE_END')
" 2>&1); then
        local end=$(date +%s)
        local duration=$((end - start))

        local tools=$(echo "$output" | grep "^TOOLS_USED:" | head -1 | sed 's/TOOLS_USED://')
        local response=$(echo "$output" | sed -n '/^RESPONSE_START$/,/^RESPONSE_END$/p' | grep -v "RESPONSE_START\|RESPONSE_END")

        if [ -n "$response" ] && [ ${#response} -gt 5 ]; then
            echo "✅ PASS (${duration}s)"
            [ -n "$tools" ] && echo "   Tools: $tools"
            echo "   Response: ${response:0:150}..."
            PASS=$((PASS + 1))
            RESULTS="$RESULTS\n✅ [$category] $name (${duration}s) tools=$tools"
        else
            echo "⚠️  WARN: Got output but response is empty/short (${duration}s)"
            echo "   Raw output tail: $(echo "$output" | tail -5)"
            WARN=$((WARN + 1))
            RESULTS="$RESULTS\n⚠️  [$category] $name (${duration}s) - empty response"
        fi
    else
        local end=$(date +%s)
        local duration=$((end - start))
        local error_tail=$(echo "$output" | tail -10)
        echo "❌ FAIL (${duration}s)"
        echo "   Error: $error_tail"
        FAIL=$((FAIL + 1))
        RESULTS="$RESULTS\n❌ [$category] $name (${duration}s) - $(echo "$error_tail" | tail -1)"
    fi

    # Brief pause between tests
    sleep 2
}

# ══════════════════════════════════════════════════════════════════════
# TEST SUITE
# ══════════════════════════════════════════════════════════════════════

echo "Running 12 capability tests..."

# 1. Knowledge (no tool needed)
run_test "knowledge" "factual_qa" \
    "What is the capital of France? Answer in one sentence."

# 2. Web Search
run_test "web_search" "basic_search" \
    "Search the web for 'Python 3.13 new features' and give me the top 3 results."

# 3. Web Extract
run_test "web_extract" "read_page" \
    "Read https://httpbin.org/html and tell me the main text content."

# 4. Terminal Command
run_test "terminal" "shell_command" \
    "Run this shell command: echo hello_from_hermes and then run date"

# 5. Execute Code
run_test "execute_code" "fibonacci" \
    "Use the execute_code tool to compute the first 15 Fibonacci numbers and return them."

# 6. File Operations
run_test "file_ops" "write_read" \
    "Write 'Hello from Hermes test' to /tmp/hermes_cap_test.txt then read it back."

# 7. Search Files
run_test "search_files" "grep_project" \
    "Search for files containing the word 'telemetry' in the current directory. List the first 3."

# 8. YouTube Search
run_test "youtube" "search" \
    "Search YouTube for 'OpenTelemetry getting started' and give me 2 results with titles."

# 9. RSS Feed
run_test "rss" "fetch_hn" \
    "Fetch the RSS feed from https://hnrss.org/newest?count=3 and list the article titles."

# 10. Memory
run_test "memory" "save_recall" \
    "Save to memory: 'capability test ran at $(date -u)'. Confirm you saved it."

# 11. Todo
run_test "todo" "create_list" \
    "Create a todo item: 'Review test results in Honeycomb'. Then list all todos."

# 12. Jina Read
run_test "jina_read" "read_example" \
    "Use jina_read to read https://example.com and tell me the heading."

# ══════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════

echo ""
echo "======================================================"
echo "  TEST RESULTS SUMMARY"
echo "======================================================"
echo ""
echo "✅ PASSED:  $PASS/12"
echo "⚠️  WARNED:  $WARN/12"
echo "❌ FAILED:  $FAIL/12"
echo ""
echo "Detailed Results:"
echo -e "$RESULTS"
echo ""
echo "======================================================"
echo "  Check Honeycomb traces at:"
echo "  https://ui.honeycomb.io/getfoolish/environments/test/datasets/hermes-agent"
echo "======================================================"
