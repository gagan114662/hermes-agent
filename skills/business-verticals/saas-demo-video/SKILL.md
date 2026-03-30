---
name: saas-demo-video
description: Creates polished 45-second SaaS product demo videos from a URL. Reads brand identity, tone, and positioning from the product site. Writes a structured video narrative. Builds animated scenes with Remotion. Exports MP4, uploads to CDN, delivers a scene breakdown doc. Triggers on: product demo, SaaS video, explainer video, Remotion, product URL, brand video, 45 second video.
version: 1.0.0
author: Hermes
license: MIT
metadata:
  hermes:
    tags: [Video, SaaS, Demo, Remotion, Marketing, Content]
---

# SaaS Demo Video Creator

> Inspired by Larry the SaaS Video Creator. One URL in — polished 45-second demo video out.

---

## 1. What This Skill Does

One command → polished 45-second SaaS product demo video:

1. Read the product URL → extract brand identity, tone, positioning, key features
2. Write a structured 45-second video narrative (8 scenes, ~5–6 seconds each)
3. Build each scene as a Remotion composition
4. Export to MP4
5. Upload to CDN (Cloudflare R2 or S3)
6. Deliver: MP4 link + full scene breakdown document

No templates. No stock footage. Every video is generated from scratch for the product.

---

## 2. Step 1 — Brand Intelligence (read the URL)

Use `jina_read` on the product URL to extract:

- **Product name** and tagline
- **Primary ICP** (who it's for)
- **Core value proposition** (what problem it solves)
- **Top 3 features** (what makes it different)
- **Tone of voice** (formal/casual, technical/accessible, bold/calm)
- **Brand colors** (from meta tags, CSS variables, or logo description)
- **Social proof** (testimonials, logos, numbers: "10,000 teams", "saves 5 hours/week")

If `jina_read` is insufficient, use `web_search` for "[product name] review features" to supplement.

Output a Brand Brief:

```
Product: [name]
Tagline: [tagline]
ICP: [who]
Problem solved: [pain]
Top features: [1, 2, 3]
Tone: [descriptor]
Primary color: [hex or description]
Social proof: [best stat or quote]
```

---

## 3. Step 2 — Video Narrative (45-second structure)

Standard 8-scene structure for SaaS demo videos:

| Scene | Duration | Purpose | Content |
|---|---|---|---|
| 1 | 0–4s | Hook / Pain | Show the painful status quo the ICP lives in |
| 2 | 4–8s | Introduce product | Product name + tagline, clean reveal |
| 3 | 8–14s | Feature 1 | Show/explain the core differentiator visually |
| 4 | 14–20s | Feature 2 | Second key benefit, motion/animation |
| 5 | 20–26s | Feature 3 | Third benefit or workflow demo |
| 6 | 26–33s | Social proof | Real stat, logo wall, or testimonial quote |
| 7 | 33–40s | Result / Transformation | Before → After, the outcome they get |
| 8 | 40–45s | CTA | Website URL + "Try free" or "Book a demo" |

Write the full script for each scene:

- Scene title
- Visual description (what's on screen)
- Voiceover/on-screen text (exact copy)
- Animation note (fade in, slide, zoom, typewriter, etc.)
- Background music mood (upbeat tech, calm professional, punchy startup)

---

## 4. Step 3 — Remotion Composition

Build the video with Remotion (React-based video creation framework).

### Project structure

```
/saas-demo-video/
├── package.json
├── remotion.config.ts
├── src/
│   ├── Root.tsx              ← registers all compositions
│   ├── DemoVideo.tsx         ← main composition (combines 8 scenes)
│   ├── scenes/
│   │   ├── Scene1Pain.tsx
│   │   ├── Scene2Intro.tsx
│   │   ├── Scene3Feature1.tsx
│   │   ├── Scene4Feature2.tsx
│   │   ├── Scene5Feature3.tsx
│   │   ├── Scene6SocialProof.tsx
│   │   ├── Scene7Result.tsx
│   │   └── Scene8CTA.tsx
│   └── components/
│       ├── AnimatedText.tsx  ← typewriter, fade-in text
│       ├── LogoWall.tsx      ← animated logo grid
│       ├── FeatureCard.tsx   ← icon + text card animation
│       └── BrandColors.ts    ← extracted brand colors as constants
```

Each scene component receives:

- `brandColors: { primary: string, secondary: string, background: string }`
- `copy: { headline: string, subtext?: string, cta?: string }`
- Frame-based animations using Remotion's `interpolate()` and `spring()`

### Standard animation patterns

```tsx
// Fade in from bottom
const opacity = interpolate(frame, [0, 20], [0, 1]);
const translateY = interpolate(frame, [0, 20], [30, 0]);

// Spring entrance
const scale = spring({ frame, fps, config: { damping: 12, mass: 0.5 } });

// Typewriter effect
const charCount = Math.floor(interpolate(frame, [0, 30], [0, text.length]));
const displayText = text.slice(0, charCount);
```

### Brand color injection

```tsx
// BrandColors.ts — populated from Step 1 extraction
export const BRAND = {
  primary: "#6366F1",      // extracted from site
  secondary: "#8B5CF6",
  text: "#FFFFFF",
  background: "#0F0F0F",
  accent: "#10B981",
};
```

---

## 5. Step 4 — Render to MP4

```bash
# Install dependencies
cd saas-demo-video && npm install

# Render to MP4 (1920x1080, 30fps, 45 seconds = 1350 frames)
npx remotion render DemoVideo out/demo.mp4 \
  --width=1920 \
  --height=1080 \
  --fps=30 \
  --frames=0-1350
```

For 1:1 (Instagram/LinkedIn):

```bash
npx remotion render DemoVideo out/demo-square.mp4 --width=1080 --height=1080
```

For 9:16 (TikTok/Reels):

```bash
npx remotion render DemoVideo out/demo-vertical.mp4 --width=1080 --height=1920
```

---

## 6. Step 5 — Upload to CDN

Upload to Cloudflare R2 (or S3):

```python
# Upload using boto3 / s3 client
import boto3

s3 = boto3.client(
    's3',
    endpoint_url='https://[account].r2.cloudflarestorage.com',
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
)

s3.upload_file(
    'out/demo.mp4',
    'hermes-media',
    f'{product_slug}/demo.mp4',
    ExtraArgs={'ContentType': 'video/mp4', 'ACL': 'public-read'}
)

cdn_url = f"https://media.hermes.ai/{product_slug}/demo.mp4"
```

---

## 7. Step 6 — Scene Breakdown Document

Create a Google Doc (or Notion page) with:

```
🎬 [Product Name] — 45-Second Demo Video
Generated: [date]
CDN URL: [link]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENE BREAKDOWN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Scene 1 (0–4s): The Pain
Visual: [description]
Copy: "[exact text]"
Animation: [type]

Scene 2 (4–8s): Product Intro
Visual: [description]
Copy: "[exact text]"
Animation: [type]

[...all 8 scenes...]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BRAND BRIEF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Brand Brief from Step 1]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VARIANTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
16:9 (website/YouTube): [CDN link]
1:1 (LinkedIn/Instagram): [CDN link]
9:16 (TikTok/Reels): [CDN link]
```

Deliver to owner via Telegram:

> "🎬 Demo video for [product] is ready.
> Watch: [CDN link]
> Scene breakdown: [doc link]
> Variants: 16:9, 1:1, 9:16 all rendered.
> Total runtime: 45s | [X] scenes | Brand colors auto-extracted."

---

## 8. Tools

| Task | Tool |
|---|---|
| Brand extraction | `jina_read`, `web_search` |
| Script writing | LLM (write directly) |
| Remotion build | `terminal_run` (npm, npx remotion) |
| CDN upload | `terminal_run` (boto3/aws cli) |
| Scene breakdown doc | Google Docs MCP / Notion MCP |
| Delivery | `send_message` (Telegram) |

---

## 9. Variations

**Ultra-short (15s):** Scenes 1, 2, 7, 8 only — for paid social ads

**Long-form (90s):** Double each scene, add a demo walkthrough in the middle (Scenes 3–5 become 8–12s each)

**No-voiceover:** All text on-screen, no audio needed — works for muted feeds

**Dark/Light mode:** Generate both variants using brand color swap

---

## 10. What You NEVER Do

- Never use stock footage — every visual is generated/animated in Remotion
- Never make up brand colors — always extract from the actual site
- Never render without checking the script with owner first for >$500 projects
- Never upload to a public URL if product is in stealth mode — check first
- Never skip the scene breakdown doc — the client needs to understand what was built and why
