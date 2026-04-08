---
name: second-brain
description: Scaffold a new domain-specific second brain vault — creates the full folder structure, CLAUDE.md config, and index. Guided wizard for naming and scoping.
version: 1.0.0
author: Hermes Agent
tags: [knowledge, second-brain, wiki, obsidian, knowledge-management]
---

# Second Brain — Scaffold Wizard

Set up a new domain-specific knowledge vault. Each vault is a dedicated second brain
for one domain — competitive intelligence, personal health, content pipeline, etc.
Dedicated vaults compound independently. One general vault is a junk drawer.

## When to Use

- User says "create a second brain", "set up a knowledge vault", "I want to track X"
- User wants to start accumulating knowledge in a specific domain
- User wants to use Obsidian with AI-maintained notes

## Steps

1. **Greet and ask the five questions** (can combine into one message):

   > Let's set up your second brain. I need five things:
   > 1. **Vault name** — short slug, e.g. `competitive-intel`, `personal-health`
   > 2. **Domain** — what will this vault track? (1-2 sentences)
   > 3. **Storage location** — default is `~/.hermes/second-brain/{name}/`, or specify custom path
   > 4. **First sources** — any files/URLs ready to drop in right away? (optional)
   > 5. **Obsidian** — do you want instructions to open this in Obsidian?

2. **Call `second_brain_scaffold(vault_name, domain)`** with the user's answers.

3. **Show the folder structure** from the tool response.

4. **Guide next steps**:
   - If they have sources ready: "Drop them into `{vault}/raw/` and I'll run `/second-brain-ingest`"
   - If they want Obsidian: "Open Obsidian → File → Open Folder → select `{vault}/wiki/`"
   - Otherwise: "When you have sources ready, just drop them in `raw/` and run `/second-brain-ingest`"

## Example Vaults

| Name | Domain |
|------|--------|
| `competitive-intel` | Competitor moves, pricing, product launches for B2B SaaS |
| `personal-health` | Lab results, supplements, workout data, doctor notes |
| `content-pipeline` | Article drafts, performance data, hooks that work |
| `client-knowledge` | Meeting transcripts, preferences, open items per client |
| `learning` | Course notes, tutorials, conference talks, concepts |

## Notes

- Check existing vaults first with `second_brain_list()` — don't duplicate
- Vault names are slugified: spaces → dashes, lowercase
- The `CLAUDE.md` file in each vault is the "brain of the system" — it tells you how to maintain it
- Remind the user they can open the vault folder in Obsidian for a visual graph view
