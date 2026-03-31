# Internal Knowledge Retrieval

## Purpose

Search across the owner's files, documents, notes, prior conversations, and saved knowledge to answer questions accurately. Always check local knowledge first before resorting to web search. Act as the owner's institutional memory — if they wrote it down, saved it, or discussed it before, you should be able to find it and cite it.

## When to Use

Activate this skill when:
- User asks a question that might be answered by their own files or notes
- User says "do we have anything on [topic]", "what did I write about [X]", "find my notes on [topic]"
- User says "what's our policy on [X]", "how do we handle [process]", "what was the decision on [topic]"
- User asks for a document, template, or reference they have used before
- Another skill needs context from the owner's knowledge base (e.g., meeting prep needs prior notes)
- User says "I know I saved something about this", "where's that document about [X]"
- User asks a factual question — check local knowledge before web search
- User says "what did we discuss about [topic] last time", "what was the outcome of [project]"

## What You Need

### Tools
- `read_file` — Read specific files when you know the path
- `search_files` — Full-text search across the owner's file system for matching content
- `write_file` — Save search results, create knowledge summaries, update indexes
- `web_search` — Fallback when local knowledge is insufficient or needs external validation
- `web_extract` — Pull content from bookmarked URLs or saved links
- `state_db` — Access stored metadata, conversation logs, decision records
- `send_message` — Deliver findings to the owner

### Data Sources (search priority order)
1. **Working documents** — Active project files, proposals, contracts, specs
2. **Meeting notes** — `meetings/` directory, prior meeting summaries and action items
3. **CRM data** — Prospect records, interaction logs, deal notes
4. **Email archives** — Saved email threads, important correspondence
5. **Personal notes** — Journal entries, brainstorms, scratch files
6. **Saved research** — Prior web research, bookmarks, reference materials
7. **Configuration and SOPs** — Business processes, playbooks, standard procedures
8. **Conversation history** — Prior interactions with Hermes (state_db)
9. **Web search** — Only after exhausting local sources

---

## Process

### Step 1: Understand the Query

Before searching, analyze what the user is actually looking for:

```
QUERY ANALYSIS:
  1. What TYPE of information?
     — Fact (specific data point, number, date)
     — Document (file, template, proposal, contract)
     — Decision (what was decided, by whom, when)
     — Process (how to do something, SOP, workflow)
     — Context (background on a topic, person, project)
     — History (what happened, timeline of events)

  2. What TIME FRAME?
     — Recent (last week/month) → prioritize recent files
     — Historical (specific date range) → search with date filters
     — Evergreen (no time constraint) → search broadly

  3. What DOMAIN?
     — Project-specific → search project directories
     — Person-specific → search CRM, meeting notes, emails
     — Business-wide → search SOPs, policies, playbooks
     — Technical → search code, configs, documentation

  4. How CERTAIN is the user it exists?
     — "I know I saved it" → it exists, find the exact file
     — "Do we have anything on" → may or may not exist, search broadly
     — General question → check local first, web fallback is fine
```

### Step 2: Search Local Knowledge (Multi-Pass)

Execute searches in priority order, stopping when you find sufficient answers:

```
PASS 1 — Exact match search
  search_files(query="{exact_phrase_from_query}")
  → Looks for the specific terms the user used
  → If found: read the matching files, extract relevant sections

PASS 2 — Synonym and related term search
  search_files(query="{synonyms_and_related_terms}")
  → Example: user asks about "pricing" → also search "rates", "fees", "cost", "quote"
  → Example: user asks about "John" → also search "John Smith", "john@company.com"
  → If found: read matches, assess relevance

PASS 3 — Directory-targeted search
  Based on query type, search specific directories:
  — Meeting-related: search_files(path="meetings/", query="{topic}")
  — CRM-related: search_files(path="crm/", query="{prospect_or_company}")
  — Project-related: search_files(path="projects/{project_name}/", query="{topic}")
  — SOPs: search_files(path="sops/", query="{process_name}")
  — Notes: search_files(path="notes/", query="{topic}")

PASS 4 — Broad semantic search
  search_files(query="{broader_topic_or_category}")
  → Cast a wider net if specific searches found nothing
  → Example: searching for "onboarding checklist" failed → try "new customer setup"

PASS 5 — State database search
  state_db(action="search", query="{topic}")
  → Check stored decisions, conversation logs, metadata
  → Prior Hermes interactions may contain the answer
```

### Step 3: Read and Extract Relevant Content

For each matching file:

```
1. Read the file:
   read_file(path=matching_file)

2. Assess relevance:
   — Does this actually answer the user's question?
   — Is this the most recent version? (check for newer files on same topic)
   — Is this authoritative? (draft vs. final, personal note vs. official doc)

3. Extract the relevant section:
   — Don't dump the entire file. Pull the specific paragraph, table, or section.
   — Preserve context: include surrounding sentences that clarify meaning.
   — Note the file path and line numbers for citation.

4. Check for conflicts:
   — If multiple files address the same topic, are they consistent?
   — If there is a conflict, present both with dates (newer is likely more accurate)
   — Flag: "Found two documents with different answers — [File A] says X, [File B] says Y."
```

### Step 4: Fill Gaps with Web Search (Fallback)

If local knowledge is insufficient:

```
1. Clearly state what was NOT found locally:
   "I searched your files for [topic] but didn't find a match. Let me check online."

2. Perform targeted web search:
   web_search(query="{refined_query}")

3. Extract relevant information:
   web_extract(url=top_result_url)

4. Clearly distinguish local vs. external sources in the response:
   — "From your files: [local info with file path]"
   — "From web search: [external info with URL]"

5. Offer to save useful web findings locally:
   "Want me to save this to your knowledge base for future reference?"
   If yes: write_file("research/{topic}/{date}-{source}.md", content)
```

### Step 5: Synthesize and Present

Compile findings into a clear, citable response:

```
1. Lead with the direct answer:
   — Don't bury the answer under methodology. Answer first, cite after.
   — If the answer is uncertain, say so upfront.

2. Cite every source:
   — Local file: "Source: /path/to/file.md (line 42-58)"
   — CRM record: "Source: CRM record for {prospect}"
   — Meeting notes: "Source: Meeting summary from {date} — /path/to/summary.md"
   — Web: "Source: {url} (retrieved {date})"

3. Note confidence level:
   — HIGH: Found in an authoritative, recent document
   — MEDIUM: Found in older notes or informal documents
   — LOW: Inferred from partial matches or external sources
   — NOT FOUND: Exhausted all sources, recommending next steps

4. Suggest related information:
   — "While searching, I also found [related document] that might be useful."
   — "Your meeting notes from {date} cover a related topic."
```

---

## Output Format

### Knowledge Retrieval Response

```
ANSWER:
{Direct answer to the user's question, 1-3 sentences}

SOURCES:
  1. {/path/to/file.md} (lines 42-58) — {brief description of what this file is}
  2. {/path/to/other-file.md} — {brief description}
  3. {url} — web source (if used)

CONFIDENCE: {HIGH / MEDIUM / LOW}

DETAILS:
{Relevant excerpt or expanded context, quoted from source}

RELATED:
  - {/path/to/related-file.md} — {why it might be relevant}
  - {/path/to/another-file.md} — {why it might be relevant}
```

### Knowledge Not Found Response

```
SEARCH RESULTS: Not found

WHAT I SEARCHED:
  1. Files matching "{query}" — 0 results
  2. Files in {directory} for "{related_terms}" — 0 results
  3. CRM and state database — 0 results
  4. Web search for "{query}" — {results found / no results}

SUGGESTIONS:
  - Do you remember where you saved this? (folder name, file type, approximate date)
  - Should I search for a different term? (possible alternatives: {list})
  - Want me to create a document on this topic from scratch?

{If web search found something useful:}
WEB RESULTS:
  I found the following online that might help:
  {summary with URL}
  Want me to save this to your knowledge base?
```

### Multi-Source Synthesis

```
ANSWER:
{Synthesized answer combining multiple sources}

SOURCE COMPARISON:
  Source 1: {/path/to/file-a.md} ({date})
    Says: {key point from this source}

  Source 2: {/path/to/file-b.md} ({date})
    Says: {key point from this source}

  {If sources conflict:}
  CONFLICT DETECTED:
    File A ({date_a}) says: {claim A}
    File B ({date_b}) says: {claim B}
    Recommendation: File B is newer — likely more current. Please confirm.

CONFIDENCE: {level}
```

---

## Examples

### Example 1: Finding a Specific Document

**Input:** "Where's that proposal I wrote for the Acme Corp deal?"

**Process:**
1. search_files(query="Acme Corp proposal") — Found: /projects/acme/proposal-v2.md
2. search_files(query="Acme proposal") — Also found: /projects/acme/proposal-v1-draft.md
3. Read both: v2 is dated March 15 (newer), v1 is dated March 8 (draft)
4. Present the most recent version with path

**Output:**
```
ANSWER: Your most recent Acme Corp proposal is at /projects/acme/proposal-v2.md (dated March 15).

SOURCES:
  1. /projects/acme/proposal-v2.md — Final proposal, $48K deal
  2. /projects/acme/proposal-v1-draft.md — Earlier draft (March 8)

CONFIDENCE: HIGH
```

### Example 2: Recalling a Decision

**Input:** "What did we decide about the API rate limits?"

**Process:**
1. search_files(query="API rate limits decision") — Found in meeting notes
2. read_file("/meetings/eng-sync/2026-03-12-summary.md") — Decision recorded
3. Cross-reference with state_db for any updates

**Output:**
```
ANSWER: In the March 12 engineering sync, the team decided on 100 req/min for free tier
and 1000 req/min for Pro tier. Decision made by Sarah, approved by CTO.

SOURCES:
  1. /meetings/eng-sync/2026-03-12-summary.md (lines 23-31)

CONFIDENCE: HIGH

RELATED:
  - /docs/api/rate-limiting-spec.md — Technical implementation spec
  - /meetings/eng-sync/2026-03-05-summary.md — Prior discussion on rate limit options
```

### Example 3: Question with No Local Answer

**Input:** "What's the current market size for AI employee tools?"

**Process:**
1. search_files(query="market size AI employee") — No results
2. search_files(query="TAM AI agents market") — No results
3. Fallback to web search: web_search("AI employee tools market size 2026")
4. Found: Multiple analyst reports with estimates

**Output:**
```
SEARCH RESULTS: Not found in your local files.

WEB RESULTS:
  According to Grand View Research, the AI agent market is projected at $XX billion
  by 2027, growing at XX% CAGR. Source: {url}

  Gartner estimates XX% of enterprises will deploy AI employee tools by 2027.
  Source: {url}

CONFIDENCE: MEDIUM (external sources, not your own data)

Want me to save this research to your knowledge base?
```

### Example 4: Process / SOP Lookup

**Input:** "How do we handle customer refund requests?"

**Process:**
1. search_files(query="refund request process") — Found: /sops/customer-refunds.md
2. read_file("/sops/customer-refunds.md") — Step-by-step process documented
3. Check for any updates or exceptions in recent notes

**Output:**
```
ANSWER: Your refund SOP is documented at /sops/customer-refunds.md. Key points:
- Refunds under $100: auto-approve
- Refunds $100-$500: require manager approval
- Refunds over $500: require owner approval
- All refunds processed within 5 business days

SOURCES:
  1. /sops/customer-refunds.md — Last updated February 10

CONFIDENCE: HIGH

NOTE: This SOP was last updated 48 days ago. Want me to check if it's still current?
```

---

## Search Strategy Tips

```
BROADENING SEARCHES:
  If exact terms fail, try:
  - Acronyms <-> full names (CRM -> Customer Relationship Management)
  - Synonyms (proposal -> pitch -> offer -> quote)
  - People's names <-> emails <-> company names
  - Project names <-> project codes <-> client names

NARROWING SEARCHES:
  If too many results, try:
  - Add date constraints (2026, March, last month)
  - Add file type filters (.md, .pdf, .doc)
  - Search specific directories first
  - Combine search terms with AND logic

COMMON SEARCH PATTERNS:
  "What did we decide about X?"  → search: "decided" + "X" in meeting notes
  "Where's the doc about X?"    → search: "X" across all files, sort by recency
  "What's our process for X?"   → search: "X" in /sops/ and /docs/
  "Who handles X?"              → search: "X" + "responsible" + "owner" in SOPs and CRM
  "When did we last talk to X?" → search: "X" in /crm/ and /meetings/, sort by date
```

## Error Handling

- **Search returns too many results**: Narrow by directory, date, or file type. Present the top 3-5 most relevant with a note that more exist.
- **File exists but is empty or corrupted**: Report the issue. Suggest checking backups or recreating the document.
- **Multiple conflicting versions**: Present both with dates. Recommend the owner reconcile and archive the outdated version.
- **User is certain a file exists but search cannot find it**: Ask for more details — approximate date, file type, directory, keywords they remember. Try alternative search terms.
- **Sensitive content found**: If a search result contains passwords, keys, or personal information, do not display it in full. Note that sensitive content was found and ask the owner how to proceed.
- **Web fallback returns low-quality results**: Say so. Do not present unreliable sources as authoritative. Recommend the owner verify independently.
