# Devin Workflow

Hermes orchestrates Devin as the coder. Hermes submits the task, monitors progress, reviews the PR, sends feedback if needed, and notifies Gagan when the PR is ready to merge.

## Trigger Phrases

Activate this skill when Gagan says:
- "devin: [task]"
- "ship [task]"
- "build [task] with devin"
- "have devin [task]"
- "use devin to [task]"

## What You Have Access To

- `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_press` — Devin web UI
- `send_message` — Telegram to Gagan (chat_id: 8444910202)
- `read_file`, `write_file` — session state at `~/.hermes/workspace/devin-sessions.json`
- skill: `github/github-code-review` — PR review after Devin finishes

## Session State File

Track active sessions in `~/.hermes/workspace/devin-sessions.json`:
```json
{
  "sessions": [
    {
      "session_url": "https://app.devin.ai/sessions/...",
      "task": "...",
      "pr_url": null,
      "feedback_rounds": 0,
      "status": "running",
      "started_at": "2026-04-02T..."
    }
  ]
}
```

---

## Phase 1 — Submit Task to Devin

1. Navigate to the homepage:
   ```
   browser_navigate("https://app.devin.ai")
   ```

2. Snapshot to confirm you're logged in:
   ```
   browser_snapshot -i
   ```
   - If you see "Log in" / "Sign up" buttons and no session history → **stop and tell Gagan**: "Hermes needs to be logged into Devin. Please log in at app.devin.ai in your browser, then let me know."
   - If you see the task input and session history → proceed

3. The task input is the large central textbox on the homepage (placeholder: "Ask Devin to build features, fix bugs, or work on your code"). Click it and type the full task:
   ```
   browser_click [textbox]
   browser_type "[task description]. Done when: a PR is open, all tests pass, and the code is ready for review."
   ```

4. Submit by clicking the blue arrow button (bottom-right of the input):
   ```
   browser_click [submit button]
   ```

5. Wait for navigation to the new session URL:
   ```
   browser_wait --load
   ```
   Capture the current URL — this is the session URL.

6. Save to session state file and notify Gagan:
   ```
   send_message(chat_id=8444910202, "🤖 Devin session started\nTask: [task]\nURL: [session_url]")
   ```

---

## Phase 2 — Monitor Progress

Poll the session every 3 minutes (use `cronjob` or loop with `terminal` sleep):

```
browser_navigate([session_url])
browser_snapshot
browser_text
```

**Look for in the page text:**

| Signal | Action |
|--------|--------|
| GitHub PR URL (`github.com/.../pull/`) | → Phase 3 (code review) |
| "I need help", "I'm blocked", "Can you clarify" | → Escalate to Gagan |
| "Session complete", "Done", "Finished" | → Check for PR URL, proceed to Phase 3 |
| No change after 20 min | → Message Gagan: "Devin seems stuck on [task]. Check: [session_url]" |
| 60 min total elapsed | → Alert Gagan, stop monitoring |

Extract PR URL from page text using `browser_js`:
```javascript
document.body.innerText.match(/https:\/\/github\.com\/[^\s]+\/pull\/\d+/)?.[0]
```

---

## Phase 3 — Code Review

Once a PR URL is found:

1. Load the `github/github-code-review` skill and run it on the PR:
   - Check out the PR branch locally
   - Apply the review checklist: correctness, security, code quality, tests, performance
   - Generate verdict: **APPROVE** or **REQUEST_CHANGES** with specific findings

2. Update session state with `pr_url`.

---

## Phase 4 — Feedback Loop

### If APPROVE:
```
send_message(chat_id=8444910202, "✅ PR ready to merge\n[PR url]\n[1-sentence summary of what was built]")
```
Update session state to `status: approved`. Done.

### If REQUEST_CHANGES:

1. Check `feedback_rounds` in session state. If ≥ 3:
   ```
   send_message(chat_id=8444910202, "⚠️ Devin hasn't resolved review issues after 3 rounds. Manual review needed.\nPR: [url]\nSession: [session_url]")
   ```
   Stop.

2. Navigate back to the Devin session:
   ```
   browser_navigate([session_url])
   browser_snapshot -i
   ```

3. Find the chat input at the bottom of the session page. Type structured feedback:
   ```
   browser_click [chat input]
   browser_type "Code review found these issues that need to be fixed before this PR can merge:

   [numbered list of specific issues with file:line references]

   Please fix each issue and push the updates to the same PR branch."
   browser_press Enter
   ```

4. Increment `feedback_rounds` in session state.

5. Return to Phase 2 to monitor Devin's fixes.

---

## Devin UI Notes

- **Homepage**: Central textbox for new tasks, blue arrow submit button at bottom-right
- **Session page**: Chat history on left/center, code editor and terminal on right panels
- **Chat input**: Bottom of the left panel — same pattern as the homepage input
- **PR links**: Appear as clickable GitHub URLs in Devin's chat messages
- **Blocked state**: Devin asks a question or says "I need clarification"
- **Login check**: If you see "Log in" button in top-right, session is not authenticated

## Auth Note

Hermes' headless browser shares a separate cookie store from your regular Chrome. To log Hermes into Devin:
1. Tell Hermes "log me into Devin" — it will open the visible browser (handoff mode)
2. Log in manually
3. Hermes resumes with the authenticated session saved

After first login, the session persists in `~/.gstack/chromium-profile/`.
