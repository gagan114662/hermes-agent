"""
Reach Tools — platform access for YouTube, Twitter/X, Reddit, RSS, and web pages.

Tools:
    youtube_get      — transcript + metadata for a YouTube URL
    youtube_search   — search YouTube, return top N results
    twitter_read     — read a tweet or thread via bird CLI
    twitter_search   — search Twitter/X via bird CLI
    reddit_read      — read a Reddit post + top comments
    reddit_search    — search Reddit (subreddit or global)
    rss_fetch        — parse any RSS or Atom feed
    jina_read        — read any URL as clean markdown via r.jina.ai

Dependencies:
    yt-dlp       — already installed
    feedparser   — installed
    bird CLI     — already installed at /opt/homebrew/bin/bird
    httpx        — already installed
    r.jina.ai    — free REST API, no key needed
"""

import glob
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile

import httpx

from tools.registry import registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list, timeout: int = 30, env: dict = None) -> tuple:
    """Run a subprocess, return (stdout, stderr)."""
    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=merged_env,
    )
    return result.stdout.strip(), result.stderr.strip()


def _ytdlp_available() -> bool:
    return shutil.which("yt-dlp") is not None


def _bird_available() -> bool:
    return shutil.which("bird") is not None


def _twitter_cookies_configured() -> bool:
    return bool(os.getenv("TWITTER_AUTH_TOKEN")) and bool(os.getenv("TWITTER_CT0"))


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------

def youtube_get_tool(url: str) -> str:
    """Get transcript and metadata for a YouTube video."""
    if not _ytdlp_available():
        return "Error: yt-dlp not found. Run: pip install yt-dlp"

    try:
        stdout, stderr = _run(
            ["yt-dlp", "--dump-json", "--no-playlist", url],
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return "Error: yt-dlp timed out fetching video info."

    if not stdout:
        return f"Error fetching video info: {stderr or 'no output'}"

    try:
        info = json.loads(stdout)
    except json.JSONDecodeError:
        return f"Error parsing yt-dlp output: {stdout[:200]}"

    title = info.get("title", "Unknown")
    uploader = info.get("uploader", "Unknown")
    duration = info.get("duration_string") or f"{info.get('duration', 0)}s"
    description = (info.get("description") or "")[:500]
    view_count = info.get("view_count", 0)
    upload_date = info.get("upload_date", "")

    # Try to get subtitles/transcript
    transcript = ""
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            _run(
                [
                    "yt-dlp",
                    "--write-auto-sub",
                    "--write-sub",
                    "--sub-lang", "en",
                    "--sub-format", "vtt",
                    "--skip-download",
                    "--no-playlist",
                    "-o", f"{tmpdir}/%(id)s",
                    url,
                ],
                timeout=30,
            )
            vtt_files = glob.glob(f"{tmpdir}/*.vtt")
            if vtt_files:
                with open(vtt_files[0]) as f:
                    raw = f.read()
                lines = []
                seen = set()
                for line in raw.splitlines():
                    line = line.strip()
                    if not line or line.startswith("WEBVTT") or "-->" in line:
                        continue
                    line = re.sub(r"<[^>]+>", "", line)
                    if line and line not in seen:
                        seen.add(line)
                        lines.append(line)
                transcript = " ".join(lines)[:3000]
        except Exception as e:
            logger.debug("Transcript fetch failed: %s", e)

    result = f"**{title}**\n"
    result += f"Channel: {uploader} | Duration: {duration} | Views: {view_count:,}\n"
    if upload_date:
        result += f"Uploaded: {upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}\n"
    if description:
        result += f"\nDescription:\n{description}\n"
    if transcript:
        result += f"\nTranscript (excerpt):\n{transcript}"
    else:
        result += "\n(No English transcript available)"

    return result


def youtube_search_tool(query: str, limit: int = 5) -> str:
    """Search YouTube and return top results."""
    if not _ytdlp_available():
        return "Error: yt-dlp not found. Run: pip install yt-dlp"

    try:
        stdout, stderr = _run(
            [
                "yt-dlp",
                "--dump-json",
                "--no-playlist",
                "--flat-playlist",
                f"ytsearch{limit}:{query}",
            ],
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return "Error: yt-dlp search timed out."

    if not stdout:
        return f"No results found. {stderr}"

    results = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            title = item.get("title", "Unknown")
            url = item.get("url") or item.get("webpage_url") or f"https://youtube.com/watch?v={item.get('id', '')}"
            duration = item.get("duration_string") or ""
            uploader = item.get("uploader") or item.get("channel") or ""
            results.append(
                f"- [{title}]({url})"
                + (f" — {uploader}" if uploader else "")
                + (f" ({duration})" if duration else "")
            )
        except json.JSONDecodeError:
            continue

    if not results:
        return "No results found."

    return f"YouTube search results for '{query}':\n" + "\n".join(results)


# ---------------------------------------------------------------------------
# Twitter / X
# ---------------------------------------------------------------------------

def twitter_read_tool(url: str) -> str:
    """Read a tweet or thread from a Twitter/X URL."""
    if not _bird_available():
        return "Error: bird CLI not installed. Run: npm install -g @steipete/bird"
    if not _twitter_cookies_configured():
        return (
            "Twitter auth not configured.\n"
            "Add to .env:\n"
            "  TWITTER_AUTH_TOKEN=<your auth_token cookie>\n"
            "  TWITTER_CT0=<your ct0 cookie>\n"
            "Get these from your browser cookies on twitter.com."
        )

    env = {
        "AUTH_TOKEN": os.environ["TWITTER_AUTH_TOKEN"],
        "CT0": os.environ["TWITTER_CT0"],
    }

    try:
        stdout, stderr = _run(["bird", "read", url, "--json"], timeout=20, env=env)
    except subprocess.TimeoutExpired:
        return "Error: bird timed out."

    if not stdout:
        return f"Error reading tweet: {stderr or 'no output'}"

    try:
        data = json.loads(stdout)
        tweets = data if isinstance(data, list) else [data]
        lines = []
        for t in tweets:
            author = t.get("user", {}).get("screen_name") or t.get("author", "")
            text = t.get("full_text") or t.get("text", "")
            created = t.get("created_at", "")
            likes = t.get("favorite_count", "")
            retweets = t.get("retweet_count", "")
            lines.append(f"@{author}: {text}")
            if created:
                lines.append(f"  {created}" + (f" · ❤️ {likes} 🔁 {retweets}" if likes else ""))
            lines.append("")
        return "\n".join(lines).strip()
    except (json.JSONDecodeError, KeyError):
        return stdout[:3000]


def twitter_search_tool(query: str, limit: int = 10) -> str:
    """Search Twitter/X for tweets matching a query."""
    if not _bird_available():
        return "Error: bird CLI not installed. Run: npm install -g @steipete/bird"
    if not _twitter_cookies_configured():
        return (
            "Twitter auth not configured.\n"
            "Add to .env:\n"
            "  TWITTER_AUTH_TOKEN=<your auth_token cookie>\n"
            "  TWITTER_CT0=<your ct0 cookie>"
        )

    env = {
        "AUTH_TOKEN": os.environ["TWITTER_AUTH_TOKEN"],
        "CT0": os.environ["TWITTER_CT0"],
    }

    try:
        stdout, stderr = _run(
            ["bird", "search", query, "--count", str(limit), "--json"],
            timeout=20,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return "Error: bird search timed out."

    if not stdout:
        return f"No results. {stderr}"

    try:
        data = json.loads(stdout)
        tweets = data if isinstance(data, list) else data.get("statuses", [data])
        lines = [f"Twitter search results for '{query}':\n"]
        for t in tweets[:limit]:
            author = t.get("user", {}).get("screen_name") or ""
            text = (t.get("full_text") or t.get("text", "")).replace("\n", " ")
            likes = t.get("favorite_count", "")
            lines.append(f"@{author}: {text}" + (f" (❤️ {likes})" if likes else ""))
        return "\n".join(lines)
    except (json.JSONDecodeError, KeyError):
        return stdout[:3000]


# ---------------------------------------------------------------------------
# Reddit
# ---------------------------------------------------------------------------

def reddit_read_tool(url: str, comment_limit: int = 10) -> str:
    """Read a Reddit post and its top comments."""
    if not url.endswith(".json"):
        url = url.rstrip("/") + ".json"
    if "?" not in url:
        url += f"?limit={comment_limit}&sort=top"

    headers = {"User-Agent": "hermes-agent/1.0 (personal use)"}
    try:
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            return "Error: Reddit blocked this request (403). Try setting HTTPS_PROXY in .env."
        return f"Error fetching Reddit post: {e}"
    except Exception as e:
        return f"Error: {e}"

    try:
        post = data[0]["data"]["children"][0]["data"]
        title = post.get("title", "")
        subreddit = post.get("subreddit", "")
        author = post.get("author", "")
        score = post.get("score", 0)
        selftext = (post.get("selftext") or "")[:1500]
        num_comments = post.get("num_comments", 0)

        result = f"**r/{subreddit}: {title}**\n"
        result += f"Posted by u/{author} | Score: {score} | {num_comments} comments\n"
        if selftext:
            result += f"\n{selftext}\n"

        comments = data[1]["data"]["children"]
        result += "\nTop comments:\n"
        count = 0
        for c in comments:
            if c.get("kind") != "t1":
                continue
            cdata = c["data"]
            cbody = (cdata.get("body") or "").replace("\n", " ")[:300]
            cauthor = cdata.get("author", "")
            cscore = cdata.get("score", 0)
            result += f"  u/{cauthor} ({cscore}): {cbody}\n"
            count += 1
            if count >= comment_limit:
                break

        return result
    except (KeyError, IndexError) as e:
        return f"Error parsing Reddit response: {e}"


def reddit_search_tool(query: str, subreddit: str = "", limit: int = 10) -> str:
    """Search Reddit. Optionally scope to a subreddit."""
    if subreddit:
        url = f"https://www.reddit.com/r/{subreddit}/search.json?q={query}&restrict_sr=1&sort=relevance&limit={limit}"
    else:
        url = f"https://www.reddit.com/search.json?q={query}&sort=relevance&limit={limit}"

    headers = {"User-Agent": "hermes-agent/1.0 (personal use)"}
    try:
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            return "Error: Reddit blocked this request (403). Try setting HTTPS_PROXY in .env."
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {e}"

    try:
        posts = data["data"]["children"]
        scope = f"r/{subreddit}" if subreddit else "Reddit"
        lines = [f"Search results for '{query}' on {scope}:\n"]
        for p in posts[:limit]:
            pd = p["data"]
            title = pd.get("title", "")
            post_url = "https://reddit.com" + pd.get("permalink", "")
            score = pd.get("score", 0)
            num_comments = pd.get("num_comments", 0)
            sub = pd.get("subreddit", "")
            lines.append(f"- **{title}** (r/{sub}, ⬆{score}, 💬{num_comments})\n  {post_url}")
        return "\n".join(lines)
    except (KeyError, IndexError) as e:
        return f"Error parsing search results: {e}"


# ---------------------------------------------------------------------------
# RSS
# ---------------------------------------------------------------------------

def rss_fetch_tool(url: str, limit: int = 10) -> str:
    """Parse an RSS or Atom feed and return the latest entries."""
    try:
        import feedparser
    except ImportError:
        return "Error: feedparser not installed. Run: pip install feedparser"

    try:
        feed = feedparser.parse(url)
    except Exception as e:
        return f"Error fetching feed: {e}"

    if feed.bozo and not feed.entries:
        return f"Error: Could not parse feed at {url}. {getattr(feed, 'bozo_exception', '')}"

    title = feed.feed.get("title", url)
    entries = feed.entries[:limit]

    lines = [f"**{title}** ({len(feed.entries)} entries)\n"]
    for e in entries:
        entry_title = e.get("title", "No title")
        entry_link = e.get("link", "")
        published = e.get("published", e.get("updated", ""))
        summary = (e.get("summary") or "")
        summary = re.sub(r"<[^>]+>", "", summary)[:200].strip()

        lines.append(f"- **{entry_title}**")
        if published:
            lines.append(f"  {published}")
        if entry_link:
            lines.append(f"  {entry_link}")
        if summary:
            lines.append(f"  {summary}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Jina Reader
# ---------------------------------------------------------------------------

def jina_read_tool(url: str) -> str:
    """Read any URL as clean markdown using Jina Reader (r.jina.ai)."""
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "Accept": "text/markdown",
        "X-Return-Format": "markdown",
    }
    jina_key = os.getenv("JINA_API_KEY", "")
    if jina_key:
        headers["Authorization"] = f"Bearer {jina_key}"

    try:
        resp = httpx.get(jina_url, headers=headers, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        content = resp.text
        if len(content) > 8000:
            content = content[:8000] + "\n\n[... truncated ...]"
        return content
    except httpx.TimeoutException:
        return f"Error: Jina Reader timed out for {url}"
    except httpx.HTTPStatusError as e:
        return f"Error: Jina Reader returned {e.response.status_code} for {url}"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------

def _check_yt_dlp() -> tuple:
    if _ytdlp_available():
        return True, "yt-dlp available"
    return False, "yt-dlp not found — run: pip install yt-dlp"


def _check_bird() -> tuple:
    if not _bird_available():
        return False, "bird CLI not installed — run: npm install -g @steipete/bird"
    if not _twitter_cookies_configured():
        return False, "Twitter cookies not set — add TWITTER_AUTH_TOKEN and TWITTER_CT0 to .env"
    return True, "bird available with Twitter auth"


def _check_always() -> tuple:
    return True, "always available"


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

registry.register(
    name="youtube_get",
    toolset="reach",
    schema={
        "name": "youtube_get",
        "description": "Get transcript and metadata for a YouTube video URL. Returns title, channel, duration, description, and English transcript if available.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "YouTube video URL"},
            },
            "required": ["url"],
        },
    },
    handler=lambda args, **kw: youtube_get_tool(args["url"]),
    check_fn=_check_yt_dlp,
    emoji="📺",
)

registry.register(
    name="youtube_search",
    toolset="reach",
    schema={
        "name": "youtube_search",
        "description": "Search YouTube and return the top matching videos with titles, URLs, channels, and durations.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results (default 5)", "default": 5},
            },
            "required": ["query"],
        },
    },
    handler=lambda args, **kw: youtube_search_tool(args["query"], args.get("limit", 5)),
    check_fn=_check_yt_dlp,
    emoji="🔍",
)

registry.register(
    name="twitter_read",
    toolset="reach",
    schema={
        "name": "twitter_read",
        "description": "Read a tweet or full thread from a Twitter/X URL. Requires TWITTER_AUTH_TOKEN and TWITTER_CT0 in .env.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Twitter/X tweet or thread URL"},
            },
            "required": ["url"],
        },
    },
    handler=lambda args, **kw: twitter_read_tool(args["url"]),
    check_fn=_check_bird,
    requires_env=["TWITTER_AUTH_TOKEN", "TWITTER_CT0"],
    emoji="🐦",
)

registry.register(
    name="twitter_search",
    toolset="reach",
    schema={
        "name": "twitter_search",
        "description": "Search Twitter/X for tweets. Requires TWITTER_AUTH_TOKEN and TWITTER_CT0 in .env.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results (default 10)", "default": 10},
            },
            "required": ["query"],
        },
    },
    handler=lambda args, **kw: twitter_search_tool(args["query"], args.get("limit", 10)),
    check_fn=_check_bird,
    requires_env=["TWITTER_AUTH_TOKEN", "TWITTER_CT0"],
    emoji="🐦",
)

registry.register(
    name="reddit_read",
    toolset="reach",
    schema={
        "name": "reddit_read",
        "description": "Read a Reddit post and its top comments from a Reddit URL.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Reddit post URL"},
                "comment_limit": {"type": "integer", "description": "Max comments to return (default 10)", "default": 10},
            },
            "required": ["url"],
        },
    },
    handler=lambda args, **kw: reddit_read_tool(args["url"], args.get("comment_limit", 10)),
    check_fn=_check_always,
    emoji="🤖",
)

registry.register(
    name="reddit_search",
    toolset="reach",
    schema={
        "name": "reddit_search",
        "description": "Search Reddit for posts. Optionally scope to a specific subreddit.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "subreddit": {"type": "string", "description": "Subreddit to search within (optional, omit for all of Reddit)"},
                "limit": {"type": "integer", "description": "Max results (default 10)", "default": 10},
            },
            "required": ["query"],
        },
    },
    handler=lambda args, **kw: reddit_search_tool(args["query"], args.get("subreddit", ""), args.get("limit", 10)),
    check_fn=_check_always,
    emoji="🔍",
)

registry.register(
    name="rss_fetch",
    toolset="reach",
    schema={
        "name": "rss_fetch",
        "description": "Fetch and parse any RSS or Atom feed URL. Returns the latest entries with titles, links, dates, and summaries.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "RSS or Atom feed URL"},
                "limit": {"type": "integer", "description": "Max entries to return (default 10)", "default": 10},
            },
            "required": ["url"],
        },
    },
    handler=lambda args, **kw: rss_fetch_tool(args["url"], args.get("limit", 10)),
    check_fn=_check_always,
    emoji="📡",
)

registry.register(
    name="jina_read",
    toolset="reach",
    schema={
        "name": "jina_read",
        "description": "Read any webpage as clean markdown using Jina Reader. Works on most pages including LinkedIn profiles, news articles, and pages that block normal scrapers. No API key required (optional JINA_API_KEY for higher rate limits).",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to read"},
            },
            "required": ["url"],
        },
    },
    handler=lambda args, **kw: jina_read_tool(args["url"]),
    check_fn=_check_always,
    emoji="🌐",
)
