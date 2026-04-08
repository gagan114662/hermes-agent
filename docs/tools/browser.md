# Browser & Web Tools

## Web Tools (`web` toolset)

Quick web access without a full browser session:

| Tool | Description |
|------|-------------|
| `web_search` | Search the web (returns up to 5 results) |
| `web_extract` | Extract a URL's content as clean markdown |

## Headless Browser (`browser` toolset)

Full Playwright-based browser for complex web interactions.

### Basic usage

```
browser_navigate(url="https://example.com")
browser_snapshot()           # get page structure with @ref IDs
browser_click(ref="@e3")     # click element
browser_type(ref="@e4", text="hello")
browser_press(key="Enter")
```

### Vision mode

```
browser_vision(question="What is the main call-to-action on this page?")
```

### File upload

```
browser_upload_file(selector="#file-input", file_path="/tmp/report.pdf")
```

### Saving images

```
browser_save_image(url="https://example.com/logo.png", save_path="/tmp/logo.png")
```

### Workflow example: web scraping

```
browser_navigate("https://news.ycombinator.com")
browser_snapshot()            # see links as @ref IDs
browser_click("@e5")          # click a story
browser_vision("summarize the article")
browser_close()
```

## Content Ingestion (`reach` toolset)

Read without a full browser:

| Tool | Description |
|------|-------------|
| `jina_read` | Clean markdown from any URL (uses Jina Reader) |
| `youtube_get` | Transcript + metadata for a YouTube video |
| `youtube_search` | Search YouTube |
| `twitter_read` | Read a tweet or thread |
| `twitter_search` | Search Twitter/X (requires `TWITTER_AUTH_TOKEN`) |
| `reddit_read` | Read a Reddit post and comments |
| `reddit_search` | Search Reddit |
| `rss_fetch` | Parse an RSS/Atom feed |
