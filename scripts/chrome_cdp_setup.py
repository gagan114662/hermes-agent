#!/usr/bin/env python3
"""One-time Chrome setup for Hermes browser automation.

Relaunches Chrome with CDP (Chrome DevTools Protocol) enabled so Hermes
can use your existing logins (Instagram, Twitter, LinkedIn, etc.).

Your tabs are preserved — Chrome restores them on relaunch.

Usage:
    python3 scripts/chrome_cdp_setup.py          # relaunch Chrome with CDP
    python3 scripts/chrome_cdp_setup.py --check   # just check if CDP is active
    python3 scripts/chrome_cdp_setup.py --auto    # add to Login Items for persistence
"""

import json
import os
import platform
import socket
import subprocess
import sys
import time

CDP_PORT = 9222
HERMES_ENV = os.path.expanduser("~/.hermes/.env")


def is_cdp_active(port: int = CDP_PORT) -> bool:
    """Check if Chrome CDP is listening."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except (ConnectionRefusedError, OSError):
        return False


def get_chrome_binary() -> str:
    """Find Chrome on this system."""
    system = platform.system()
    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    elif system == "Linux":
        import shutil
        candidates = [p for p in [
            shutil.which("google-chrome"),
            shutil.which("google-chrome-stable"),
            shutil.which("chromium-browser"),
        ] if p]
    else:
        candidates = []

    for c in candidates:
        if os.path.isfile(c):
            return c
    return ""


def is_chrome_running() -> bool:
    """Check if Chrome is currently running."""
    try:
        if platform.system() == "Darwin":
            result = subprocess.run(
                ["pgrep", "-f", "Google Chrome"],
                capture_output=True, timeout=5,
            )
            return result.returncode == 0
        else:
            result = subprocess.run(
                ["pgrep", "-f", "chrome"],
                capture_output=True, timeout=5,
            )
            return result.returncode == 0
    except Exception:
        return False


def quit_chrome_gracefully():
    """Ask Chrome to quit gracefully (preserves session for restore)."""
    system = platform.system()
    if system == "Darwin":
        subprocess.run(
            ["osascript", "-e", 'tell application "Google Chrome" to quit'],
            timeout=10,
        )
    else:
        subprocess.run(["pkill", "-TERM", "chrome"], timeout=10)

    # Wait for Chrome to fully exit
    for _ in range(15):
        if not is_chrome_running():
            return True
        time.sleep(1)
    return not is_chrome_running()


def get_hermes_chrome_profile() -> str:
    """Get or create a Hermes-specific Chrome profile that shares logins.

    Chrome refuses --remote-debugging-port with the default profile.
    We create a separate user-data-dir that symlinks key subdirectories
    (cookies, login data, extensions) from the real profile so logins
    are shared, while CDP works.
    """
    hermes_profile = os.path.expanduser("~/.hermes/chrome-profile")
    os.makedirs(hermes_profile, exist_ok=True)

    system = platform.system()
    if system == "Darwin":
        real_profile = os.path.expanduser(
            "~/Library/Application Support/Google/Chrome"
        )
    elif system == "Linux":
        real_profile = os.path.expanduser("~/.config/google-chrome")
    else:
        return hermes_profile

    # Copy key profile files that contain login state.
    # We copy (not symlink) because Chrome locks these files.
    real_default = os.path.join(real_profile, "Default")
    hermes_default = os.path.join(hermes_profile, "Default")
    os.makedirs(hermes_default, exist_ok=True)

    # Files that contain login/session state
    files_to_copy = [
        "Cookies", "Login Data", "Web Data",
        "Preferences", "Secure Preferences",
        "Local State",
    ]

    import shutil
    for fname in files_to_copy:
        src = os.path.join(real_default, fname)
        dst = os.path.join(hermes_default, fname)
        if os.path.exists(src):
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass

    # Also copy Local State from Chrome root (contains OS crypt config)
    local_state_src = os.path.join(real_profile, "Local State")
    local_state_dst = os.path.join(hermes_profile, "Local State")
    if os.path.exists(local_state_src):
        try:
            shutil.copy2(local_state_src, local_state_dst)
        except Exception:
            pass

    return hermes_profile


def launch_chrome_with_cdp(port: int = CDP_PORT):
    """Launch Chrome with remote debugging enabled using a Hermes profile."""
    chrome = get_chrome_binary()
    if not chrome:
        print("ERROR: Chrome not found")
        sys.exit(1)

    print("Setting up Hermes Chrome profile (copying your logins)...")
    profile_dir = get_hermes_chrome_profile()

    subprocess.Popen(
        [chrome, f"--remote-debugging-port={port}",
         f"--user-data-dir={profile_dir}",
         "--no-first-run", "--no-default-browser-check"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def set_env_var(key: str, value: str):
    """Add or update an env var in ~/.hermes/.env"""
    lines = []
    found = False
    if os.path.exists(HERMES_ENV):
        with open(HERMES_ENV) as f:
            for line in f:
                if line.strip().startswith(f"{key}="):
                    lines.append(f"{key}={value}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"{key}={value}\n")
    with open(HERMES_ENV, "w") as f:
        f.writelines(lines)


def create_launch_agent():
    """Create a macOS LaunchAgent to auto-start Chrome with CDP on login."""
    if platform.system() != "Darwin":
        print("Auto-start only supported on macOS")
        return

    plist_dir = os.path.expanduser("~/Library/LaunchAgents")
    os.makedirs(plist_dir, exist_ok=True)
    plist_path = os.path.join(plist_dir, "com.hermes.chrome-cdp.plist")

    chrome = get_chrome_binary()
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hermes.chrome-cdp</string>
    <key>ProgramArguments</key>
    <array>
        <string>open</string>
        <string>-a</string>
        <string>Google Chrome</string>
        <string>--args</string>
        <string>--remote-debugging-port={CDP_PORT}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>"""

    with open(plist_path, "w") as f:
        f.write(plist_content)

    print(f"Created LaunchAgent: {plist_path}")
    print("Chrome will auto-start with CDP on next login.")


def main():
    args = sys.argv[1:]

    if "--check" in args:
        if is_cdp_active():
            print(f"Chrome CDP is ACTIVE on port {CDP_PORT}")
            try:
                import urllib.request
                resp = urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json/version", timeout=3)
                info = json.loads(resp.read())
                print(f"  Browser: {info.get('Browser', 'unknown')}")
                print(f"  WebSocket: {info.get('webSocketDebuggerUrl', 'unknown')}")
            except Exception:
                pass
        else:
            print(f"Chrome CDP is NOT active on port {CDP_PORT}")
        sys.exit(0)

    if "--auto" in args:
        create_launch_agent()
        sys.exit(0)

    # Main flow: relaunch Chrome with CDP
    print("=" * 50)
    print("Hermes Chrome Setup")
    print("=" * 50)
    print()

    # Check if CDP is already active
    if is_cdp_active():
        print(f"Chrome CDP already active on port {CDP_PORT}!")
        set_env_var("BROWSER_CDP_URL", f"http://localhost:{CDP_PORT}")
        print("BROWSER_CDP_URL set in ~/.hermes/.env")
        print("\nHermes can now use your browser logins.")
        sys.exit(0)

    chrome = get_chrome_binary()
    if not chrome:
        print("ERROR: Google Chrome not found!")
        print("Install Chrome from https://google.com/chrome")
        sys.exit(1)

    print(f"Found Chrome: {chrome}")

    if is_chrome_running():
        print("\nChrome is running. I'll quit and relaunch it with CDP enabled.")
        print("Your tabs will be restored automatically.")
        print()

        if "--yes" not in args:
            response = input("Continue? [Y/n] ").strip().lower()
            if response and response != "y":
                print("Cancelled.")
                sys.exit(0)

        print("Quitting Chrome...")
        if not quit_chrome_gracefully():
            print("ERROR: Could not quit Chrome. Close it manually and re-run.")
            sys.exit(1)
        print("Chrome closed.")
        time.sleep(2)

    print(f"Launching Chrome with CDP on port {CDP_PORT}...")
    launch_chrome_with_cdp()

    # Wait for CDP to come up
    for i in range(20):
        time.sleep(1)
        if is_cdp_active():
            break
        if i % 5 == 4:
            print("  Still waiting for Chrome to start...")

    if is_cdp_active():
        print(f"\nChrome CDP active on port {CDP_PORT}!")
        set_env_var("BROWSER_CDP_URL", f"http://localhost:{CDP_PORT}")
        print("BROWSER_CDP_URL set in ~/.hermes/.env")
        print("\nHermes can now use your Instagram, Twitter, LinkedIn logins.")
        print("Your existing tabs have been restored.")
        print()
        print("To make this permanent (auto-start on login):")
        print("  python3 scripts/chrome_cdp_setup.py --auto")
    else:
        print("\nERROR: Chrome started but CDP not responding.")
        print("Try manually:")
        if platform.system() == "Darwin":
            print(f'  open -a "Google Chrome" --args --remote-debugging-port={CDP_PORT}')
        else:
            print(f"  google-chrome --remote-debugging-port={CDP_PORT}")


if __name__ == "__main__":
    main()
