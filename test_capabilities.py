#!/usr/bin/env python3
"""
Hermes Agent Capability Tester
Runs the agent through a battery of tests across different tool categories.
All calls emit OpenTelemetry traces to Honeycomb for observability.
"""

import asyncio
import json
import os
import sys
import time
import traceback
from datetime import datetime

# Load env
from dotenv import load_dotenv
load_dotenv('.env')

from run_agent import AIAgent

# ── Test Prompts by Category ─────────────────────────────────────────────────
# Each test: (category, test_name, prompt, expect_tool_call)
TESTS = [
    # ── Core: Web Search ──
    ("web_search", "basic_web_search",
     "Search the web for 'latest Python 3.13 release date' and tell me what you find. Be concise.",
     True),

    # ── Core: Web Extract / Read ──
    ("web_extract", "read_webpage",
     "Read this webpage and summarize it in 2 sentences: https://httpbin.org/html",
     True),

    # ── Core: Terminal / Code Execution ──
    ("terminal", "run_shell_command",
     "Run `echo hello_from_hermes && python3 -c \"print(2+2)\"` in the terminal and show me the output.",
     True),

    # ── Core: Execute Code (Python) ──
    ("execute_code", "python_calculation",
     "Use the execute_code tool to compute the first 20 Fibonacci numbers and return them as a list.",
     True),

    # ── Core: File Operations ──
    ("file_ops", "write_and_read_file",
     "Write a file called /tmp/hermes_test.txt with the content 'Hello from Hermes Agent test!' then read it back and confirm the contents.",
     True),

    # ── Core: Search Files ──
    ("search_files", "search_project_files",
     "Search for files in the current directory that contain the word 'telemetry'. List the first 5 matches.",
     True),

    # ── Knowledge: No-tool question ──
    ("knowledge", "factual_question",
     "What is the capital of France? Answer in one sentence, no tools needed.",
     False),

    # ── YouTube ──
    ("youtube", "youtube_search",
     "Search YouTube for 'OpenTelemetry tutorial' and give me the top 3 results with titles.",
     True),

    # ── Reddit ──
    ("reddit", "reddit_search",
     "Search Reddit for 'best python testing framework 2024' and summarize the top result.",
     True),

    # ── RSS ──
    ("rss", "rss_fetch",
     "Fetch the RSS feed from https://hnrss.org/newest?count=3 and list the 3 article titles.",
     True),

    # ── Memory ──
    ("memory", "save_memory",
     "Save to memory: 'Test run started at " + datetime.now().isoformat() + "'. Confirm you saved it.",
     True),

    # ── Vision ──
    ("vision", "analyze_image",
     "Analyze this image URL and describe what you see: https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Camponotus_flavomarginatus_ant.jpg/320px-Camponotus_flavomarginatus_ant.jpg",
     True),

    # ── Todo ──
    ("todo", "create_todo",
     "Create a todo item: 'Review Honeycomb traces for test run'. Then list all todos.",
     True),

    # ── Wiki ──
    ("wiki", "wiki_ingest_and_query",
     "Ingest this text into the wiki with title 'Test Entry': 'Hermes Agent is a self-improving AI agent built by Nous Research. It supports 130+ tools.' Then query the wiki for 'Hermes Agent'.",
     True),

    # ── Jina Read ──
    ("jina_read", "jina_webpage_read",
     "Use jina_read to read https://example.com and give me the main heading text.",
     True),

    # ── Delegate Task (subagent) ──
    ("delegate", "delegate_simple_task",
     "Delegate this task to a subagent: 'Calculate 137 * 42 + 19 and return just the number.'",
     True),

    # ── Process (multi-step) ──
    ("process", "multi_step_process",
     "Process this: Search the web for 'Nous Research Hermes', then write a 2-sentence summary to /tmp/nous_summary.txt",
     True),
]


def create_agent():
    """Create an AIAgent instance with Z.ai GLM on the Codeplan endpoint."""
    return AIAgent(
        base_url='https://api.z.ai/api/coding/paas/v4',
        model='glm-4.7',
        api_key=os.environ.get('GLM_API_KEY'),
    )


def run_single_test(agent, category, test_name, prompt, expect_tool_call):
    """Run a single test and return results dict."""
    result = {
        "category": category,
        "test_name": test_name,
        "prompt": prompt,
        "expect_tool_call": expect_tool_call,
        "status": "unknown",
        "response": None,
        "tool_calls_made": [],
        "error": None,
        "duration_seconds": 0,
        "timestamp": datetime.now().isoformat(),
    }

    print(f"\n{'='*70}")
    print(f"TEST: [{category}] {test_name}")
    print(f"PROMPT: {prompt[:80]}...")
    print(f"{'='*70}")

    start = time.monotonic()
    try:
        # run_conversation() returns a dict: {final_response, messages, api_calls, completed}
        raw_result = agent.run_conversation(prompt)
        elapsed = time.monotonic() - start
        result["duration_seconds"] = round(elapsed, 2)

        # Extract the text response from the result dict
        if isinstance(raw_result, dict):
            response_text = raw_result.get("final_response", "") or raw_result.get("content", "") or ""
            conversation_messages = raw_result.get("messages", [])
        elif isinstance(raw_result, str):
            response_text = raw_result
            conversation_messages = []
        else:
            response_text = str(raw_result)
            conversation_messages = []

        result["response"] = response_text[:500] if response_text else "(empty)"

        # Extract tool calls from the returned messages (not agent.messages)
        tool_calls = []
        for msg in conversation_messages:
            if isinstance(msg, dict) and msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                    tool_calls.append(fn.get("name", "unknown"))

        # Fallback: check agent's internal session messages
        if not tool_calls and hasattr(agent, "_session_messages"):
            for msg in agent._session_messages:
                if isinstance(msg, dict) and msg.get("role") == "assistant" and msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                        tool_calls.append(fn.get("name", "unknown"))

        result["tool_calls_made"] = tool_calls

        # Determine pass/fail
        if response_text and len(str(response_text).strip()) > 5:
            if expect_tool_call and not tool_calls:
                result["status"] = "WARN"  # Got response but no tool calls when expected
                print(f"⚠️  WARN: Expected tool call but none made")
            else:
                result["status"] = "PASS"
                print(f"✅ PASS ({elapsed:.1f}s)")
        else:
            result["status"] = "FAIL"
            print(f"❌ FAIL: Empty or very short response")

        if tool_calls:
            print(f"   Tools used: {', '.join(tool_calls)}")
        print(f"   Response preview: {str(response_text or '')[:150]}...")

    except Exception as e:
        elapsed = time.monotonic() - start
        result["duration_seconds"] = round(elapsed, 2)
        result["status"] = "ERROR"
        result["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"💥 ERROR ({elapsed:.1f}s): {result['error']}")
        traceback.print_exc()

    return result


def main():
    print(f"\n{'#'*70}")
    print(f"# HERMES AGENT CAPABILITY TEST SUITE")
    print(f"# Started: {datetime.now().isoformat()}")
    print(f"# Model: glm-4.7 (Z.ai Codeplan)")
    print(f"# Tests: {len(TESTS)}")
    print(f"{'#'*70}\n")

    results = []

    for i, (category, test_name, prompt, expect_tool) in enumerate(TESTS):
        print(f"\n>>> Running test {i+1}/{len(TESTS)}...")

        # Create fresh agent for each test (clean conversation state)
        agent = create_agent()

        result = run_single_test(agent, category, test_name, prompt, expect_tool)
        results.append(result)

        # Small delay between tests to avoid rate limiting
        time.sleep(2)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n\n{'#'*70}")
    print(f"# TEST RESULTS SUMMARY")
    print(f"{'#'*70}\n")

    passed = [r for r in results if r["status"] == "PASS"]
    warned = [r for r in results if r["status"] == "WARN"]
    failed = [r for r in results if r["status"] == "FAIL"]
    errored = [r for r in results if r["status"] == "ERROR"]

    print(f"✅ PASSED:  {len(passed)}/{len(results)}")
    print(f"⚠️  WARNED:  {len(warned)}/{len(results)}")
    print(f"❌ FAILED:  {len(failed)}/{len(results)}")
    print(f"💥 ERRORED: {len(errored)}/{len(results)}")

    if warned:
        print(f"\n⚠️  Warnings:")
        for r in warned:
            print(f"   [{r['category']}] {r['test_name']}: {r.get('error') or 'Expected tool call but none made'}")

    if failed:
        print(f"\n❌ Failures:")
        for r in failed:
            print(f"   [{r['category']}] {r['test_name']}: {r.get('error') or 'Empty response'}")

    if errored:
        print(f"\n💥 Errors:")
        for r in errored:
            print(f"   [{r['category']}] {r['test_name']}: {r['error']}")

    print(f"\n⏱️  Total time: {sum(r['duration_seconds'] for r in results):.1f}s")
    print(f"📊 Average per test: {sum(r['duration_seconds'] for r in results)/len(results):.1f}s")

    # Category breakdown
    print(f"\n📋 By Category:")
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r["status"])
    for cat, statuses in sorted(categories.items()):
        emoji = "✅" if all(s == "PASS" for s in statuses) else "❌"
        print(f"   {emoji} {cat}: {', '.join(statuses)}")

    # Save detailed results
    output_path = "/tmp/hermes_test_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n📁 Detailed results saved to: {output_path}")

    return results


if __name__ == "__main__":
    main()
