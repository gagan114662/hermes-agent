"""
Desktop Tools — control the visible Terminal.app and other macOS UI via AppleScript.

Tools:
    terminal_run        — run a command in the visible Terminal.app window (user can see it)
    terminal_type       — type text/keystrokes into the frontmost Terminal window without pressing Enter
    claude_code_send    — type a message into the Claude Code session and press Enter (drives this session)
"""

import logging
import subprocess

from tools.registry import registry

logger = logging.getLogger(__name__)


def _osascript(script: str) -> tuple[bool, str]:
    """Run an AppleScript and return (success, output)."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        return False, result.stderr.strip()
    return True, result.stdout.strip()


def terminal_run_tool(command: str) -> str:
    """
    Run a shell command in the visible Terminal.app window so the user can see it execute.
    Opens Terminal if not already open.
    """
    safe_cmd = command.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        'tell application "Terminal"\n'
        '    activate\n'
        '    if (count of windows) = 0 then\n'
        f'        do script "{safe_cmd}"\n'
        '    else\n'
        f'        do script "{safe_cmd}" in front window\n'
        '    end if\n'
        'end tell'
    )
    ok, out = _osascript(script)
    if ok:
        return f"Ran in Terminal: {command}"
    return f"Error running in Terminal: {out}"


def terminal_type_tool(text: str) -> str:
    """
    Type text into the frontmost Terminal.app window without pressing Enter.
    Useful for partially typing a command for the user to review before running.
    """
    safe_text = text.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        'tell application "Terminal"\n'
        '    activate\n'
        'end tell\n'
        'tell application "System Events"\n'
        f'    keystroke "{safe_text}"\n'
        'end tell'
    )
    ok, out = _osascript(script)
    if ok:
        return f"Typed into Terminal: {text}"
    return f"Error typing into Terminal: {out}"


def claude_code_send_tool(message: str) -> str:
    """
    Type a message into the Claude Code session running in Terminal and press Enter.
    Finds the Terminal window whose title contains 'claude --dangerously-skip-permissions'.
    """
    safe_msg = message.replace("\\", "\\\\").replace('"', '\\"')
    # Find and focus the Claude Code window, then type the message + Return
    script = (
        'tell application "Terminal"\n'
        '    set claudeWin to missing value\n'
        '    repeat with w in windows\n'
        '        if name of w contains "claude --dangerously" then\n'
        '            set claudeWin to w\n'
        '            exit repeat\n'
        '        end if\n'
        '    end repeat\n'
        '    if claudeWin is missing value then\n'
        '        return "error: Claude Code window not found"\n'
        '    end if\n'
        '    set index of claudeWin to 1\n'
        '    activate\n'
        'end tell\n'
        'delay 0.3\n'
        'tell application "System Events"\n'
        f'    keystroke "{safe_msg}"\n'
        '    key code 36\n'
        'end tell'
    )
    ok, out = _osascript(script)
    if not ok:
        return f"Error sending to Claude Code: {out}"
    if "error:" in out:
        return out
    return f"Sent to Claude Code: {message}"


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

registry.register(
    name="terminal_run",
    toolset="desktop",
    schema={
        "name": "terminal_run",
        "description": (
            "Run a shell command in the user's visible Terminal.app window so they can watch it execute. "
            "Use this when the user asks you to 'run X in my terminal', 'type X in the terminal', "
            "or when you want the user to see the command and its output live. "
            "This opens Terminal if needed and types + runs the command visibly."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to run in the visible Terminal window",
                },
            },
            "required": ["command"],
        },
    },
    handler=lambda args, **kw: terminal_run_tool(args["command"]),
    check_fn=lambda: (True, "always available on macOS"),
    emoji="💻",
)

registry.register(
    name="terminal_type",
    toolset="desktop",
    schema={
        "name": "terminal_type",
        "description": (
            "Type text into the frontmost Terminal.app window WITHOUT pressing Enter. "
            "Use this to pre-fill a command for the user to review and run themselves."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to type into the Terminal window",
                },
            },
            "required": ["text"],
        },
    },
    handler=lambda args, **kw: terminal_type_tool(args["text"]),
    check_fn=lambda: (True, "always available on macOS"),
    emoji="⌨️",
)

registry.register(
    name="claude_code_send",
    toolset="desktop",
    schema={
        "name": "claude_code_send",
        "description": (
            "Send a message directly into the Claude Code session running in the user's Terminal. "
            "This finds the Claude Code window, focuses it, types the message, and presses Enter — "
            "so Claude Code receives and acts on it immediately. "
            "Use this to drive Claude Code to build features, fix bugs, or run tasks on behalf of the user."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message or instruction to send to Claude Code",
                },
            },
            "required": ["message"],
        },
    },
    handler=lambda args, **kw: claude_code_send_tool(args["message"]),
    check_fn=lambda: (True, "always available on macOS"),
    emoji="🤖",
)
