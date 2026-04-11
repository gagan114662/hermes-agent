---
name: second-brain-lint
description: Audit a vault's wiki health — broken links, orphan pages, unprocessed raw files, and stub pages. Run monthly or after bulk ingests to keep the wiki clean.
version: 1.0.0
author: Hermes Agent
tags: [knowledge, second-brain, lint, wiki, maintenance]
---

# Second Brain — Wiki Health Check

Audit a vault for structural issues. Errors compound just as fast as knowledge does —
a broken link or orphan page that goes unfixed becomes 10 broken links in 3 months.

## When to Use

- User says "lint my second brain", "check the wiki", "audit my vault"
- After a bulk ingest of many sources
- Monthly maintenance
- Before exporting or sharing a vault

## Steps

1. **Identify the vault**:
   - If user specified, use it
   - Otherwise call `second_brain_list()` and ask
   - If only one vault exists, use it automatically

2. **Run the audit**: `second_brain_lint(vault_name)`

3. **Present results by category**:

   | Issue | Meaning | Fix |
   |-------|---------|-----|
   | Broken links | `[[ref]]` pointing to non-existent page | Delete the link or create the missing page |
   | Orphan pages | Pages not linked anywhere | Add to index.md or link from a related page |
   | Unprocessed raw | Files in raw/ with no sources/ page | Run second_brain_ingest on them |
   | Stub pages | Pages with <50 chars, likely empty | Re-ingest the source or delete the stub |

4. **Offer to fix each category**:

   For broken links:
   > I found {N} broken links. Want me to remove them from the affected pages?

   For orphan pages:
   > I found {N} orphan pages. Want me to add them to the index?

   For unprocessed raw files:
   > {N} files in raw/ haven't been ingested. Want me to run second_brain_ingest_all?

   For stubs:
   > {N} stub pages found. Want me to delete them or flag them for re-ingestion?

5. **If all checks pass**:
   > Vault '{name}' is healthy — {N} pages, no issues found.

## Auto-Fix Operations

When user approves a fix:

- **Remove broken links**: Use `read_file` + `patch` to edit the affected .md files
- **Add orphans to index**: Call `write_file` to update `wiki/index.md`
- **Ingest unprocessed**: Call `second_brain_ingest_all(vault_name)`
- **Delete stubs**: Use `terminal` to `rm` the stub files (confirm with user first)

## Notes

- Lint is read-only — it only reports, never auto-modifies without user approval
- Run after every bulk ingest of 5+ sources
- Monthly lint is the recommended cadence for active vaults
- A vault with 0 issues is a vault that will actually be useful in 6 months
