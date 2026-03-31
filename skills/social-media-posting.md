# Social Media Posting via Browser Automation

You are posting content to social media platforms using the user's existing browser sessions. The user is already logged into their accounts in Chrome. You use Hermes browser automation tools to navigate, interact with page elements, and publish posts.

---

## Available Browser Tools

```
browser_navigate(url, task_id)    — Load a URL
browser_snapshot(task_id=...)     — Get accessibility tree of current page (element refs like @e1, @e2)
browser_click(ref, task_id)       — Click an element by ref
browser_type(ref, text, task_id)  — Type text into an input field
browser_press(key, task_id)       — Press a keyboard key (Enter, Tab, Escape, etc.)
browser_scroll(direction, task_id)— Scroll up or down
browser_back(task_id)             — Navigate back
browser_vision(question, task_id) — Take a screenshot and answer a visual question about the page
browser_console(task_id=...)      — Read JS console messages
browser_upload_file(file_path, task_id) — Upload a file to a <input type="file"> on the page (bypasses OS file picker)
browser_close(task_id)            — Close the browser session
```

## Image Generation via Browser (Google AI Studio)

Hermes generates images by opening Google AI Studio in the browser (the user is already logged in) and using the UI. No API keys needed.

**Full workflow: Generate Image → Save to Disk → Post to Instagram**

```
Step 1: Generate in AI Studio
  browser_navigate("https://aistudio.google.com/prompts/new_chat", task_id=task_id)
  browser_snapshot(task_id=task_id)
  — Find the prompt input area
  — browser_type(ref, "Generate an image: [your prompt here]", task_id=task_id)
  — browser_press("Enter", task_id=task_id) or click Send/Generate
  — Wait for image generation (may take 10-30 seconds)
  — browser_snapshot to check if image appeared

Step 2: Save image from page to disk
  browser_save_image(css_selector="img", filename="instagram_post.png", task_id=task_id)
  — Returns: {"success": true, "file_path": "~/.hermes/generated-images/instagram_post.png"}
  — This bypasses the OS save dialog by extracting image data via CDP

Step 3: Navigate to Instagram and upload
  browser_navigate("https://www.instagram.com/", task_id=task_id)
  — Click Create button
  — browser_upload_file(file_path="~/.hermes/generated-images/instagram_post.png", task_id=task_id)
  — This bypasses the OS file picker by setting the file via CDP
  — Continue with crop → caption → share (see Instagram steps below)
```

**Key tools for this workflow:**
```
browser_save_image(css_selector, filename, task_id) — Save an image from the page to disk (no OS dialog)
browser_upload_file(file_path, task_id)              — Upload a file to a <input type="file"> (no OS dialog)
```

**Key concept:** `browser_snapshot` returns an accessibility tree with element references like `@e5`. You use these refs with `browser_click` and `browser_type` to interact with specific elements.

---

## Pre-Posting Checklist (Run Before Every Post)

1. **Navigate** to the platform URL
2. **Snapshot** the page to get element refs
3. **Check login status** — look for profile avatar, username, or compose elements in the snapshot
4. If NOT logged in (you see a login form or "Sign up" prompts):
   - Tell the user: "You are not logged in to [platform]. Please log in at [URL] in your Chrome browser, then tell me to continue."
   - STOP and wait for confirmation
5. If logged in, proceed with posting

---

## Platform: Twitter / X

### Character Limits
- Tweet: 280 characters (free), 25,000 characters (Premium)
- Images: up to 4 per tweet
- Video: up to 2 min 20 sec (free), 4 hours (Premium)

### Posting Steps

```
Step 1: Navigate
  browser_navigate("https://x.com/home", task_id=task_id)

Step 2: Snapshot to verify login
  browser_snapshot(task_id=task_id)
  — Look for: "Post" button, compose area, profile avatar, "What is happening?!" placeholder
  — If you see "Sign in" or "Create account": user is NOT logged in. Stop and ask.

Step 3: Find and click the compose area
  — In the snapshot, look for a textbox or element with text like "What is happening?!"
  — browser_click(ref_of_compose_area, task_id=task_id)

Step 4: Type the tweet text
  — browser_type(ref_of_compose_area, "Your tweet text here", task_id=task_id)

Step 5: Post the tweet
  — In a fresh snapshot, find the "Post" button (it is a button element, NOT the nav link)
  — The Post button for the compose area is usually near the bottom of the compose box
  — browser_click(ref_of_post_button, task_id=task_id)

Step 6: Verify
  — Wait 2 seconds, then browser_snapshot or browser_vision("Was the tweet posted successfully?")
  — Look for: the compose area resetting to empty, or a toast/notification saying "Your post was sent"
  — If you see an error, report it to the user
```

### Common Issues
- **"Something went wrong"**: Rate limit or duplicate tweet. Wait 60 seconds and try different wording.
- **Multiple "Post" buttons**: The page has Post buttons in the nav sidebar AND in the compose area. Use the one inside the compose box (usually lower in the accessibility tree, near the character count).
- **Thread posting**: After posting the first tweet, click "Add another post" or the reply compose area, type the next tweet, and post again.

### Compose via URL shortcut
You can also use `https://x.com/intent/tweet?text=URL_ENCODED_TEXT` to pre-fill the compose box, then just click Post.

---

## Platform: Instagram

### Character Limits
- Caption: 2,200 characters
- Hashtags: 30 max (5-10 recommended)
- Stories text: keep it short and readable

### Image Upload — SOLVED

**`browser_upload_file` bypasses the native OS file picker entirely.** It uses Chrome DevTools Protocol to set files directly on the hidden `<input type="file">` element. No manual user intervention needed.

**Full automated flow:**
1. Generate image with `google_image_generate` or `image_generate` → get file_path
2. Navigate to Instagram → click Create → the upload dialog appears
3. Use `browser_upload_file(file_path)` to set the image on the file input
4. Instagram picks it up automatically → proceed to crop, caption, share

### Posting Steps (Feed Post with Image)

```
Step 1: Generate the image (if needed)
  google_image_generate(prompt="...", aspect_ratio="post")
  — Returns: {"success": true, "file_path": "/Users/.../.hermes/generated-images/gemini_xxx.png"}
  — Save the file_path for Step 5

Step 2: Navigate
  browser_navigate("https://www.instagram.com/", task_id=task_id)

Step 3: Snapshot to verify login
  browser_snapshot(task_id=task_id)
  — Look for: profile avatar, home/search/explore icons, "Create" or "New post" button
  — If you see "Log in" or "Sign up": user is NOT logged in. Stop and ask.

Step 4: Click "Create" (the + icon or "Create" in sidebar)
  — Look for: element with text "Create" or "New post" or a "+" icon in the left sidebar
  — browser_click(ref_of_create_button, task_id=task_id)

Step 5: Upload the image file (NO manual file picker needed!)
  — A modal appears with "Drag photos and videos here" and a "Select from computer" button
  — DO NOT click "Select from computer" (that opens the OS file picker which you can't control)
  — Instead, use browser_upload_file directly:
    browser_upload_file(file_path="/Users/.../.hermes/generated-images/gemini_xxx.png", task_id=task_id)
  — This sets the file on Instagram's hidden <input type="file"> element via CDP
  — Instagram will automatically detect the file and show the crop/edit screen

Step 6: Crop screen
  — Snapshot. You should see crop options and a "Next" button.
  — browser_click(ref_of_next_button, task_id=task_id)

Step 7: Filter screen (optional)
  — Snapshot. Apply filter if requested, or skip.
  — browser_click(ref_of_next_button, task_id=task_id)

Step 8: Write caption
  — Snapshot. Find the caption textarea (usually labeled "Write a caption..." or similar)
  — browser_click(ref_of_caption_area, task_id=task_id)
  — browser_type(ref_of_caption_area, "Your caption with #hashtags here", task_id=task_id)

Step 9: Share
  — Find and click the "Share" button
  — browser_click(ref_of_share_button, task_id=task_id)

Step 10: Verify
  — Wait 3-5 seconds. Snapshot or use browser_vision("Was the Instagram post shared successfully?")
  — Look for: "Your post has been shared" message, or redirect back to feed
```

### Instagram Stories
```
— After Step 3, look for "Story" option instead of "Post"
— Same file upload limitation applies
— After uploading media, look for text/sticker tools
— Find and click "Share to Story" or "Your Story" button
```

### Instagram Reels
```
— After Step 3, look for "Reel" tab in the create dialog
— Same file upload limitation applies
— After uploading video, add caption on the details screen
— Click "Share" to publish the reel
```

---

## Platform: LinkedIn

### Character Limits
- Post: 3,000 characters
- Article: no practical limit
- Comment: 1,250 characters

### Posting Steps

```
Step 1: Navigate
  browser_navigate("https://www.linkedin.com/feed/", task_id=task_id)

Step 2: Snapshot to verify login
  browser_snapshot(task_id=task_id)
  — Look for: profile photo, "Start a post" box, "Home" / "My Network" nav items
  — If you see "Join now" or "Sign in": user is NOT logged in. Stop and ask.

Step 3: Click "Start a post"
  — Find the element with text "Start a post" or the compose box at the top of the feed
  — browser_click(ref_of_start_a_post, task_id=task_id)

Step 4: Type the post content
  — A modal/editor opens. Snapshot to find the text editor area.
  — The editor is usually a contenteditable div or a textbox
  — browser_click(ref_of_editor, task_id=task_id)
  — browser_type(ref_of_editor, "Your LinkedIn post content here", task_id=task_id)

Step 5: (Optional) Add media
  — Look for media icons (image, video, document) at the bottom of the compose modal
  — If adding an image: same file picker limitation as Instagram. Guide the user.

Step 6: Post
  — Find the "Post" button in the compose modal
  — browser_click(ref_of_post_button, task_id=task_id)

Step 7: Verify
  — Wait 2 seconds. Snapshot.
  — Look for: the modal closing, your post appearing at the top of the feed
  — browser_vision("Did the LinkedIn post publish successfully?", task_id=task_id)
```

### LinkedIn Articles
```
— Navigate to https://www.linkedin.com/feed/
— Click "Write article" (below the compose box or in a dropdown)
— This opens the article editor (separate page)
— Snapshot to find the title field and body editor
— Type the title, then click the body area and type/paste article content
— Click "Publish" when done
— Articles support rich formatting, images, and longer content
```

### Common Issues
- **Visibility selector**: LinkedIn may show a visibility dropdown ("Anyone", "Connections only"). Default is "Anyone" which is fine for most posts.
- **Hashtag suggestions**: LinkedIn auto-suggests hashtags as you type `#`. You can dismiss these or click to accept.
- **Draft saving**: LinkedIn auto-saves drafts. If you see a "resume draft?" prompt on opening compose, either continue it or dismiss it.

---

## Platform: Facebook

### Character Limits
- Post: 63,206 characters
- Comment: 8,000 characters

### Posting Steps

```
Step 1: Navigate
  browser_navigate("https://www.facebook.com/", task_id=task_id)

Step 2: Snapshot to verify login
  browser_snapshot(task_id=task_id)
  — Look for: profile name/avatar, "What's on your mind?" compose box, News Feed
  — If you see "Log in" or "Create new account": user is NOT logged in. Stop and ask.

Step 3: Click "What's on your mind?"
  — Find the element with text "What's on your mind, [Name]?" or similar
  — browser_click(ref_of_compose_prompt, task_id=task_id)

Step 4: Type the post content
  — A "Create post" modal opens. Snapshot to find the text area.
  — browser_click(ref_of_text_area, task_id=task_id)
  — browser_type(ref_of_text_area, "Your Facebook post content here", task_id=task_id)

Step 5: (Optional) Add photo/video
  — Look for "Photo/video" button in the modal
  — Same file picker limitation. Guide the user.

Step 6: Post
  — Find the "Post" button at the bottom of the modal
  — browser_click(ref_of_post_button, task_id=task_id)

Step 7: Verify
  — Wait 2-3 seconds. Snapshot.
  — Look for: modal closing, post appearing in feed
  — browser_vision("Did the Facebook post publish successfully?", task_id=task_id)
```

### Posting to a Facebook Page (not personal profile)
```
— Navigate to the Page: browser_navigate("https://www.facebook.com/YourPageName", task_id=task_id)
— Or go to: https://www.facebook.com/pages/?category=your_pages
— Click "Create post" on the page
— Same flow as above, but content publishes as the Page, not your personal profile
— Check: some pages have a "Switch" button to toggle between posting as yourself vs as the Page
```

### Common Issues
- **Privacy selector**: Facebook may show audience selector (Public, Friends, Only me). Check before posting.
- **Marketplace/Groups redirect**: If the user lands on Marketplace or Groups, navigate explicitly to `https://www.facebook.com/?filter=all` for the main feed.
- **Business Suite redirect**: Facebook may redirect business accounts to Meta Business Suite. If this happens, navigate to `https://www.facebook.com/` directly.

---

## Cross-Platform Posting Workflow

When the user asks you to post the same content across multiple platforms:

```
1. Prepare platform-specific versions of the content:
   — Twitter: Concise, under 280 chars. Front-load the hook. 1-3 hashtags max.
   — Instagram: Visual-first caption. Line breaks for readability. 5-10 hashtags at the end.
   — LinkedIn: Professional tone. Longer form is fine. Use line breaks and whitespace. 3-5 hashtags.
   — Facebook: Conversational. Medium length. Minimal or no hashtags.

2. Post in this order (most restrictive first):
   a. Twitter (most likely to fail due to character limits or rate limits)
   b. Instagram (requires user interaction for file upload)
   c. LinkedIn
   d. Facebook

3. After each successful post, confirm to the user before moving to the next platform.

4. Provide a summary when done:
   "Posted to:
   - Twitter: [posted / failed — reason]
   - Instagram: [posted / failed — reason]
   - LinkedIn: [posted / failed — reason]
   - Facebook: [posted / failed — reason]"
```

---

## Content Adaptation Rules

When adapting a single message for multiple platforms:

| Platform   | Tone         | Length       | Hashtags   | Emojis    | Links         |
|------------|-------------|-------------|------------|-----------|---------------|
| Twitter/X  | Punchy      | < 280 chars | 1-3        | Sparingly | Shortened URL |
| Instagram  | Visual/warm | 100-300 words| 5-10      | Yes       | "Link in bio" |
| LinkedIn   | Professional| 200-500 words| 3-5       | Minimal   | Full URL OK   |
| Facebook   | Casual      | 100-300 words| 0-3       | Yes       | Full URL OK   |

---

## Error Recovery

If posting fails at any step:

1. **Take a snapshot** to understand the current page state
2. **Use browser_vision** to visually inspect what happened
3. **Common recoveries:**
   - Page didn't load: `browser_navigate` again
   - Element not found: `browser_snapshot` with `full=True` to see all elements
   - Button unresponsive: try `browser_press("Enter")` as alternative
   - Modal blocked view: press `Escape` to dismiss, then retry
   - CAPTCHA appeared: tell the user "A CAPTCHA appeared. Please solve it in your browser, then tell me to continue."
   - Session expired: tell the user to log in again
4. **Never retry more than 3 times** without asking the user

---

## Verification Best Practice

After every post, always verify with TWO methods:

1. `browser_snapshot` — check the accessibility tree for success indicators
2. `browser_vision("Was the post published successfully?")` — visual confirmation via screenshot

Only report success to the user when at least one verification method confirms the post went through.

---

## What You NEVER Do

- Never store or log the user's passwords or session tokens
- Never navigate to phishing or unofficial login pages
- Never post without the user's explicit approval of the content
- Never bypass CAPTCHA or security checks programmatically
- Never click "Boost" or "Promote" buttons (these cost money)
- Never change account settings, profile info, or privacy settings
- Never accept follow requests or friend requests without asking
- Never delete existing posts unless explicitly asked
