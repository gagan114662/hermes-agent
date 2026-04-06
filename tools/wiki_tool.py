"""
Business Wiki Tool — Karpathy LLM-Wiki Pattern

The AI employee maintains a persistent, self-updating knowledge base about the
business it works for. Every interaction (calls, emails, WhatsApp, CRM logs)
is automatically woven into interlinked markdown wiki pages.

Unlike RAG (which searches raw text), the wiki stores *synthesized* knowledge:
patterns, facts, relationships, and insights that compound over time.

Structure:
    ~/.hermes/wiki/
        index.md          — master index with links to all pages
        clients.md        — who they are, patterns, preferences
        products.md       — what the business sells, pricing, features
        objections.md     — common objections + winning responses
        competitors.md    — competitive intel
        faq.md            — frequently asked questions + answers
        processes.md      — how things work (booking, payment, etc.)
        <custom>.md       — any page the AI decides to create

Tools:
    wiki_update(content, source)   — feed new info, AI updates relevant pages
    wiki_query(question)           — ask the wiki a question
    wiki_read(page_name)           — read a full page
    wiki_list()                    — list all wiki pages
    wiki_ingest(text, source)      — bulk ingest (calls, transcripts, etc.)
"""

import json
import os
import re
import threading
import urllib.request
from datetime import datetime
from pathlib import Path

from tools.registry import registry

# ── storage ───────────────────────────────────────────────────────────────────

def _wiki_dir() -> Path:
    d = Path(os.path.expanduser("~/.hermes/wiki"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_page(name: str) -> str:
    """Read a wiki page. Returns empty string if it doesn't exist."""
    path = _wiki_dir() / f"{name}.md"
    return path.read_text() if path.exists() else ""


def _write_page(name: str, content: str) -> None:
    path = _wiki_dir() / f"{name}.md"
    path.write_text(content)


def _list_pages() -> list[str]:
    return [p.stem for p in sorted(_wiki_dir().glob("*.md"))]


# ── ollama ────────────────────────────────────────────────────────────────────

def _ollama(prompt: str, timeout: int = 90) -> str:
    model = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        f"{base}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()).get("response", "").strip()
    except Exception as e:
        return f"Error: {e}"


# ── core wiki logic ───────────────────────────────────────────────────────────

_DEFAULT_PAGES = {
    "index": "# Business Wiki\n\nThis wiki is maintained automatically by the AI employee.\n\n## Pages\n\n- [Clients](clients.md)\n- [Products](products.md)\n- [Objections](objections.md)\n- [Competitors](competitors.md)\n- [FAQ](faq.md)\n- [Processes](processes.md)\n",
    "clients": "# Clients\n\n*No data yet. Will be populated from interactions.*\n",
    "products": "# Products & Services\n\n*No data yet.*\n",
    "objections": "# Common Objections & Responses\n\n*No data yet.*\n",
    "competitors": "# Competitor Intel\n\n*No data yet.*\n",
    "faq": "# Frequently Asked Questions\n\n*No data yet.*\n",
    "processes": "# Business Processes\n\n*No data yet.*\n",
}


def _ensure_defaults() -> None:
    for name, content in _DEFAULT_PAGES.items():
        if not (_wiki_dir() / f"{name}.md").exists():
            _write_page(name, content)


def _determine_pages_to_update(content: str, existing_pages: list[str]) -> list[str]:
    """Ask Ollama which wiki pages should be updated given new content."""
    prompt = f"""You are managing a business knowledge wiki. New information has arrived:

---
{content[:800]}
---

Existing wiki pages: {', '.join(existing_pages)}

Which pages should be updated with this information? Return ONLY a comma-separated list of page names (no explanation). Example: clients,faq

If the information doesn't fit any existing page, you may suggest a new page name (one or two words, lowercase, no spaces — use underscores)."""

    result = _ollama(prompt, timeout=30)
    pages = [p.strip().lower().replace(" ", "_") for p in result.split(",")]
    return [p for p in pages if p and re.match(r'^[a-z_]+$', p)]


def _update_page_with_content(page_name: str, new_content: str, source: str) -> None:
    """Read a wiki page and ask Ollama to merge the new information into it."""
    existing = _read_page(page_name) or f"# {page_name.replace('_', ' ').title()}\n\n"

    prompt = f"""You are maintaining a business knowledge wiki page called "{page_name}".

CURRENT PAGE CONTENT:
{existing}

NEW INFORMATION (from {source}):
{new_content[:1000]}

Your task:
- Merge the new information into the page
- Keep existing information, update if contradicted
- Use clear markdown headings and bullet points
- Be concise — facts only, no filler text
- If something is now out of date, remove or correct it
- Link to related pages using [[page_name]] syntax

Return the COMPLETE updated page content (including the # heading). Nothing else."""

    updated = _ollama(prompt, timeout=90)
    if updated and not updated.startswith("Error"):
        _write_page(page_name, updated)


# ── update queue (background, non-blocking) ───────────────────────────────────

_update_queue: list[tuple[str, str]] = []
_queue_lock = threading.Lock()
_worker_running = False


def _background_worker() -> None:
    global _worker_running
    while True:
        with _queue_lock:
            if not _update_queue:
                _worker_running = False
                return
            content, source = _update_queue.pop(0)

        _ensure_defaults()
        pages = _list_pages()
        pages_to_update = _determine_pages_to_update(content, pages)

        for page in pages_to_update[:3]:  # max 3 pages per update to stay fast
            try:
                _update_page_with_content(page, content, source)
            except Exception:
                pass


def _enqueue_update(content: str, source: str) -> None:
    global _worker_running
    with _queue_lock:
        _update_queue.append((content, source))
        if not _worker_running:
            _worker_running = True
            t = threading.Thread(target=_background_worker, daemon=True)
            t.start()


# ── public tool functions ─────────────────────────────────────────────────────

def wiki_update(content: str, source: str = "manual") -> str:
    """
    Feed new information into the wiki. The AI reads it and updates the
    relevant pages in the background. Non-blocking — returns immediately.

    Call this after every significant interaction:
      - End of a phone call (summary)
      - Customer email or WhatsApp message
      - After a sales meeting
      - Competitor pricing discovered
    """
    _ensure_defaults()
    if len(content) < 10:
        return "Error: content too short to add to wiki."

    _enqueue_update(content, source)
    return f"Wiki update queued from [{source}] ({len(content)} chars). Pages will update in background."


def wiki_query(question: str) -> str:
    """
    Ask the business wiki a question. Searches all pages and synthesizes an answer.

    Examples:
      "What do clients usually object to about pricing?"
      "What's our refund policy?"
      "Who are our main competitors and how do we differ?"
      "What does client John Smith prefer?"
    """
    _ensure_defaults()
    pages = _list_pages()

    # Read all pages (skip empty ones)
    wiki_content = []
    for page in pages:
        text = _read_page(page)
        if text and "*No data yet*" not in text and len(text) > 50:
            wiki_content.append(f"=== {page}.md ===\n{text}")

    if not wiki_content:
        return "The wiki is empty. Feed it interactions with wiki_update() first."

    combined = "\n\n".join(wiki_content)[:4000]  # fit in context

    prompt = f"""You are answering a question using a business wiki.

WIKI CONTENT:
{combined}

QUESTION: {question}

Answer based only on what's in the wiki. If the answer isn't there, say so clearly.
Be concise and direct."""

    answer = _ollama(prompt, timeout=60)
    return answer if answer else "Could not generate answer from wiki."


def wiki_read(page_name: str) -> str:
    """Read a specific wiki page. Use wiki_list() to see available pages."""
    _ensure_defaults()
    page_name = page_name.lower().replace(" ", "_").replace(".md", "")
    content = _read_page(page_name)
    if not content:
        return f"Page '{page_name}' does not exist. Available: {', '.join(_list_pages())}"
    return content


def wiki_list() -> str:
    """List all wiki pages with their size and last modified time."""
    _ensure_defaults()
    lines = ["Business Wiki Pages:\n"]
    for page in _list_pages():
        path = _wiki_dir() / f"{page}.md"
        size = path.stat().st_size
        mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        lines.append(f"  {page}.md  ({size} bytes, updated {mtime})")
    lines.append(f"\nWiki location: {_wiki_dir()}")
    lines.append("Use wiki_read(page_name) to read a page.")
    return "\n".join(lines)


def wiki_ingest(text: str, source: str = "transcript") -> str:
    """
    Bulk ingest a long document (call transcript, email thread, meeting notes)
    into the wiki. Splits into chunks and processes each one.

    Good for:
      - Full call transcripts
      - Long email threads
      - Onboarding documents
      - Product manuals
    """
    _ensure_defaults()
    if len(text) < 20:
        return "Error: text too short."

    # Split into ~500-char chunks with overlap
    chunk_size = 500
    chunks = []
    for i in range(0, len(text), chunk_size - 50):
        chunk = text[i:i + chunk_size]
        if chunk.strip():
            chunks.append(chunk)

    for chunk in chunks:
        _enqueue_update(chunk, source)

    return (
        f"Queued {len(chunks)} chunks from [{source}] for wiki ingestion. "
        f"Pages will update in background over the next few minutes."
    )


# ── auto-hook for crm_log ─────────────────────────────────────────────────────

def crm_log_wiki_hook(phone: str, channel: str, summary: str, contact_name: str = "") -> None:
    """Called automatically after every crm_log to update the wiki."""
    content = f"Interaction via {channel} with {contact_name or phone}: {summary}"
    _enqueue_update(content, source=f"crm_log:{channel}")


# ── registry ──────────────────────────────────────────────────────────────────

registry.register(
    name="wiki_update",
    toolset="crm",
    schema={
        "name": "wiki_update",
        "description": "Feed new information into the business wiki. The AI reads it and updates the relevant knowledge pages in the background (non-blocking). Call this after every meaningful interaction — calls, emails, discoveries.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The new information to add to the wiki (interaction summary, fact, discovery, etc.)"},
                "source": {"type": "string", "description": "Where this information came from (e.g. 'phone_call', 'email', 'whatsapp', 'meeting')"},
            },
            "required": ["content"],
        },
    },
    handler=lambda args, **kw: wiki_update(
        content=args["content"],
        source=args.get("source", "manual"),
    ),
)

registry.register(
    name="wiki_query",
    toolset="crm",
    schema={
        "name": "wiki_query",
        "description": "Ask the business knowledge wiki a question. Returns answers synthesized from all accumulated business knowledge. Use this before answering client questions to give informed, consistent responses.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The question to answer from the business wiki"},
            },
            "required": ["question"],
        },
    },
    handler=lambda args, **kw: wiki_query(question=args["question"]),
)

registry.register(
    name="wiki_read",
    toolset="crm",
    schema={
        "name": "wiki_read",
        "description": "Read a full wiki page. Use wiki_list() to see available pages. Good for reviewing all known info on a topic (clients, products, competitors, etc.)",
        "parameters": {
            "type": "object",
            "properties": {
                "page_name": {"type": "string", "description": "Page name to read (e.g. clients, products, objections, competitors, faq, processes)"},
            },
            "required": ["page_name"],
        },
    },
    handler=lambda args, **kw: wiki_read(page_name=args["page_name"]),
)

registry.register(
    name="wiki_list",
    toolset="crm",
    schema={
        "name": "wiki_list",
        "description": "List all business wiki pages with their size and last update time.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: wiki_list(),
)

registry.register(
    name="wiki_ingest",
    toolset="crm",
    schema={
        "name": "wiki_ingest",
        "description": "Bulk ingest a long document (call transcript, email thread, meeting notes, product manual) into the business wiki. Splits into chunks and processes each one in the background.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The full document text to ingest"},
                "source": {"type": "string", "description": "Source label (e.g. 'call_transcript', 'email_thread', 'product_manual')"},
            },
            "required": ["text"],
        },
    },
    handler=lambda args, **kw: wiki_ingest(
        text=args["text"],
        source=args.get("source", "transcript"),
    ),
)
