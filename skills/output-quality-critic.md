# Output Quality Critic

## Purpose

Self-review every piece of external communication before it leaves the system. Check emails, social posts, proposals, follow-ups, and outreach against quality standards: tone match, factual accuracy, grammar, brand consistency, and call-to-action clarity. Score each output 1-10 and auto-fix issues that score below 8. This is the last line of defense against embarrassing mistakes.

## When to Use

Activate this skill when:
- Any email is about to be sent to an external recipient
- Any social media post is about to be published
- Any proposal or contract is about to be delivered to a prospect
- Any follow-up communication is being drafted after a meeting
- Any outreach message is ready for cold or warm leads
- User says "review this before sending", "check this draft", "is this good to go"
- Another skill produces output that will be seen by someone outside the organization
- Any automated response is about to be sent (auto-replies, triage responses)

**This skill should run automatically as a pre-send gate. No communication leaves without a quality check.**

## What You Need

### Tools
- `read_file` — Load the business profile, brand guidelines, tone preferences, prior communications
- `search_files` — Find prior messages to the same recipient for tone consistency
- `web_search` — Verify factual claims, check current pricing, validate company info
- `write_file` — Log quality scores, save corrected versions, update quality metrics
- `state_db` — Retrieve business context, customer tier, relationship history

### Reference Data
- **Business profile** — Company name, value proposition, industry, key differentiators
- **Tone guide** — Formal vs casual scale, vocabulary preferences, phrases to avoid
- **Brand guidelines** — Logo usage (for attachments), color (for HTML emails), voice characteristics
- **Recipient context** — Who is this going to? Their tier, relationship, communication history
- **Factual anchors** — Current pricing, product capabilities, team names, correct URLs

---

## Process

### Step 1: Classify the Output

Before reviewing, determine what type of communication this is:

```
OUTPUT TYPES AND STANDARDS:

  EMAIL — EXTERNAL CLIENT/CUSTOMER
    Tone: Professional, warm, responsive
    Length: 50-200 words ideal
    Required: greeting, substance, clear next step, sign-off
    Stakes: HIGH — represents the business directly

  EMAIL — INVESTOR/VIP
    Tone: Professional, confident, data-informed
    Length: 50-150 words ideal
    Required: warmth, specificity, no vague promises
    Stakes: CRITICAL — trust and credibility on the line

  EMAIL — COLD OUTREACH
    Tone: Professional, personalized, concise
    Length: 40-100 words ideal
    Required: personalization, value prop, single clear CTA
    Stakes: HIGH — first impression, determines if they engage

  SOCIAL MEDIA POST
    Tone: Platform-appropriate (see platform rules)
    Length: Platform-specific limits
    Required: hook, value, CTA (if promotional)
    Stakes: MEDIUM — public and permanent

  PROPOSAL/CONTRACT
    Tone: Formal, precise, thorough
    Length: As needed
    Required: accuracy in pricing, scope, terms, dates
    Stakes: CRITICAL — legal and financial implications

  FOLLOW-UP (post-meeting)
    Tone: Warm, action-oriented, concise
    Length: 100-200 words ideal
    Required: accurate recap, correct action items, correct names
    Stakes: HIGH — misquoting decisions or names damages credibility

  INTERNAL TEAM MESSAGE
    Tone: Direct, clear, friendly
    Length: Brief as possible
    Required: clarity, correct tagging
    Stakes: LOW — but still matters for team trust
```

### Step 2: Run Quality Checks

Score each dimension 1-10. The output must score 8+ on every dimension to pass.

#### Check 1: Tone Match (1-10)

```
EVALUATION CRITERIA:
  - Does the tone match the recipient's relationship tier?
    → VIP/investor: warm but professional, never casual
    → Customer Tier 1: personal, attentive, high-touch
    → Customer Tier 2: friendly, helpful, efficient
    → Cold prospect: professional, concise, not salesy
    → Internal team: direct, clear, optional warmth

  - Does the tone match prior communications with this person?
    → search_files(query="to:{recipient_email}")
    → Compare formality level, greeting style, sign-off style
    → If prior emails used "Hey Sarah", don't switch to "Dear Ms. Chen"

  - Does the tone match the situation?
    → Apology: empathetic, not defensive
    → Good news: enthusiastic but not over-the-top
    → Bad news: honest, empathetic, solution-oriented
    → Routine: efficient, not overly formal

COMMON TONE FAILURES:
  - Too casual for the recipient's tier
  - Too formal for an established warm relationship
  - Robotic or template-sounding (no personalization)
  - Overly enthusiastic (exclamation marks overload)
  - Passive-aggressive or defensive undertone
  - Generic flattery ("I hope this email finds you well")

SCORING:
  10 = Pitch-perfect tone for this specific recipient and situation
  8-9 = Good tone, minor adjustments possible
  6-7 = Acceptable but noticeable issues — auto-fix
  4-5 = Wrong tone — would feel off to the recipient — auto-fix
  1-3 = Completely inappropriate tone — block and rewrite
```

#### Check 2: Factual Accuracy (1-10)

```
VERIFY EVERY CLAIM:
  1. Names — Are all names spelled correctly?
     → Cross-reference with CRM, email headers, LinkedIn
     → Common failures: wrong first name, misspelled last name, wrong title

  2. Dates and times — Are all dates correct?
     → Meeting dates match calendar
     → Deadlines are accurate and achievable
     → Time zones are specified where needed

  3. Numbers — Are all figures accurate?
     → Pricing matches current rate card
     → Metrics match actual data
     → Deal values match CRM records

  4. Company info — Are all company references correct?
     → Company name spelled correctly (including capitalization: GitHub not Github)
     → Product names are accurate
     → Competitor names are correct (never confuse competitors)

  5. Commitments — Are promises realistic?
     → Don't promise delivery dates without checking with the team
     → Don't commit to features that don't exist
     → Don't guarantee outcomes that aren't certain

  6. Links and URLs — Do they work?
     → If a URL is included, verify it is correct
     → web_search or web_extract to confirm the link is live

SCORING:
  10 = Every fact verified and correct
  8-9 = All major facts correct, minor details unchecked but likely fine
  6-7 = One factual issue found — auto-fix before sending
  4-5 = Multiple factual issues — block, fix, and re-review
  1-3 = Critical factual error (wrong name, wrong price, false claim) — block
```

#### Check 3: Grammar and Clarity (1-10)

```
CHECK FOR:
  1. Spelling errors — run spell check
  2. Grammar issues — subject-verb agreement, tense consistency, pronoun clarity
  3. Punctuation — proper use of commas, periods, apostrophes
  4. Sentence length — break up sentences longer than 25 words
  5. Paragraph length — no paragraph longer than 3-4 sentences in email
  6. Jargon — avoid unexplained acronyms or technical terms for non-technical recipients
  7. Passive voice — prefer active voice ("We will send" not "It will be sent")
  8. Filler words — remove "just", "actually", "basically", "I think", "I feel like"
  9. Redundancy — remove "in order to" (use "to"), "at this point in time" (use "now")
  10. Clarity — could a busy person understand this in one read?

READABILITY TARGETS:
  Email to executive: Grade 8-10 reading level, short paragraphs
  Email to technical person: Grade 10-12, precise terminology ok
  Social media post: Grade 6-8, conversational
  Proposal: Grade 10-12, professional precision

SCORING:
  10 = Flawless grammar, crystal clear, perfect structure
  8-9 = Minor issues that don't affect comprehension
  6-7 = Noticeable issues — auto-fix
  4-5 = Hard to read or multiple errors — auto-fix
  1-3 = Incomprehensible or embarrassingly error-filled — block and rewrite
```

#### Check 4: Brand Consistency (1-10)

```
CHECK AGAINST BRAND GUIDELINES:
  1. Company name — Always written correctly (exact capitalization, spacing)
  2. Product names — Correct naming convention used
  3. Value proposition — Claims align with actual product/service capabilities
  4. Voice — Matches brand personality (innovative, trustworthy, friendly, etc.)
  5. Prohibited phrases — None of the blacklisted words or phrases used
  6. Competitor mentions — Never disparage competitors directly
  7. Legal compliance — No unauthorized guarantees, disclaimers present where needed
  8. Sign-off — Consistent with brand standard (name, title, contact info)

COMMON BRAND FAILURES:
  - Inconsistent company name spelling across the same email
  - Claiming features that don't exist or are unreleased
  - Using competitor brand names in a negative context
  - Making legal or financial guarantees without authorization
  - Inconsistent sign-off format

SCORING:
  10 = Perfect brand alignment, consistent voice, all guidelines followed
  8-9 = Minor deviation, still clearly on-brand
  6-7 = Noticeable inconsistency — auto-fix
  4-5 = Off-brand or potentially misleading — auto-fix
  1-3 = Brand-damaging content — block
```

#### Check 5: Call-to-Action Clarity (1-10)

```
EVERY EXTERNAL COMMUNICATION SHOULD HAVE A CLEAR NEXT STEP:

  1. Is there a CTA?
     — If not, should there be? (Not every email needs one, but most should)

  2. Is the CTA specific?
     — BAD: "Let me know what you think"
     — GOOD: "Can you reply by Friday with your preferred time slot?"

  3. Is there exactly ONE primary CTA?
     — Multiple CTAs confuse. Pick the most important one.
     — Secondary options can be mentioned but should not compete.

  4. Is the CTA easy to act on?
     — Does it require minimal effort from the recipient?
     — Is the next step obvious? (click this link, reply with X, book here)

  5. Is the CTA appropriate for the relationship stage?
     — Cold outreach: low-commitment CTA (reply, quick call, check this link)
     — Warm prospect: medium (schedule a demo, review proposal)
     — Active customer: direct (approve, sign, confirm)

SCORING:
  10 = Clear, specific, easy-to-act-on CTA appropriate for the context
  8-9 = CTA present and mostly clear, minor improvement possible
  6-7 = CTA vague or missing — auto-fix by adding/sharpening
  4-5 = Multiple competing CTAs or inappropriate ask — auto-fix
  1-3 = No CTA at all when one is clearly needed — add before sending
```

### Step 3: Calculate Overall Score and Decide

```
AGGREGATE SCORING:

  Overall score = Minimum of all 5 dimension scores
  (The chain is only as strong as its weakest link)

  PASS (score 8-10 on ALL dimensions):
    → Approve for sending
    → Log the quality score
    → No changes needed

  AUTO-FIX (any dimension scores 5-7):
    → Apply fixes automatically
    → Re-score after fixes
    → If all dimensions now 8+: approve
    → If still below 8: escalate to owner for review

  BLOCK (any dimension scores 1-4):
    → Do NOT send
    → Notify the owner: "Blocked [output type] to [recipient]. Issue: [specific problem]."
    → Rewrite or ask the owner to revise
    → Re-review after revision

  CRITICAL BLOCK (factual accuracy scores 1-4):
    → Immediate block — factual errors are the most damaging
    → Highlight the specific error
    → Require manual owner approval even after fix
```

### Step 4: Apply Auto-Fixes

When a dimension scores 5-7, apply targeted fixes:

```
TONE FIXES:
  - Adjust formality level (add/remove casual language)
  - Fix greeting to match relationship (Dear → Hi, or vice versa)
  - Remove exclamation marks if too many (max 1 per email)
  - Add warmth if too cold ("Thanks for reaching out" openers)
  - Remove filler if too wordy

FACTUAL FIXES:
  - Correct name spellings from CRM data
  - Fix dates from calendar
  - Update pricing from rate card
  - Remove unverifiable claims

GRAMMAR FIXES:
  - Fix spelling errors
  - Fix grammar issues
  - Shorten long sentences
  - Break up long paragraphs
  - Remove filler words

BRAND FIXES:
  - Correct company/product name capitalization
  - Remove unauthorized claims
  - Add standard sign-off if missing

CTA FIXES:
  - Add CTA if missing
  - Sharpen vague CTA to specific ask
  - Remove competing CTAs (keep strongest one)
```

### Step 5: Log Quality Metrics

```
After every review, log:

write_file("quality/reviews/{date}-{output_type}-{recipient}.md", {
  date: today,
  output_type: "email/social/proposal",
  recipient: recipient_name,
  scores: {
    tone: X,
    accuracy: X,
    grammar: X,
    brand: X,
    cta: X,
    overall: X
  },
  issues_found: ["list of issues"],
  fixes_applied: ["list of fixes"],
  result: "approved/auto-fixed/blocked",
  time_to_review: "Xs"
})

WEEKLY QUALITY REPORT:
  Track trends:
  - Average quality score by output type
  - Most common issues (which dimension fails most often?)
  - Auto-fix rate (what percentage needed fixes?)
  - Block rate (what percentage was blocked?)
  - Improvement trend (are scores getting better over time?)
```

---

## Output Format

### Quality Review Report

```
QUALITY REVIEW — {output_type} to {recipient}
==============================================

SCORES:
  Tone match:        {score}/10 {PASS/FIX/BLOCK}
  Factual accuracy:  {score}/10 {PASS/FIX/BLOCK}
  Grammar/clarity:   {score}/10 {PASS/FIX/BLOCK}
  Brand consistency: {score}/10 {PASS/FIX/BLOCK}
  CTA clarity:       {score}/10 {PASS/FIX/BLOCK}
  ─────────────────────────────
  OVERALL:           {min_score}/10

RESULT: {APPROVED / AUTO-FIXED / BLOCKED}

{If issues found:}
ISSUES:
  1. {Dimension}: {specific issue} → {fix applied or recommendation}
  2. {Dimension}: {specific issue} → {fix applied or recommendation}

{If auto-fixed:}
CHANGES MADE:
  - Line 3: Changed "Hey" to "Hi Sarah" (tone — more appropriate for Tier 1 customer)
  - Line 7: Fixed "Acme corp" to "Acme Corp" (brand — correct capitalization)
  - Line 12: Added deadline to CTA — "Can you confirm by Thursday?" (CTA clarity)

{If blocked:}
BLOCKED — REQUIRES REVISION:
  Critical issue: {what is wrong}
  Recommended fix: {how to fix it}
  Please revise and resubmit for review.
```

---

## Examples

### Example 1: Email Passes Review

**Output being reviewed:** Follow-up email to Tier 1 customer after a meeting.

**Review:**
```
Tone match:        9/10 PASS — warm, professional, matches prior emails to this person
Factual accuracy:  10/10 PASS — names correct, dates match calendar, pricing accurate
Grammar/clarity:   9/10 PASS — clear, concise, good structure
Brand consistency: 10/10 PASS — company name correct, no unauthorized claims
CTA clarity:       8/10 PASS — clear next step, could be slightly more specific

OVERALL: 8/10 — APPROVED
```

### Example 2: Cold Outreach Auto-Fixed

**Output being reviewed:** Cold outreach email to a prospect.

**Review:**
```
Tone match:        7/10 FIX — too casual for first contact ("Hey!" opener)
Factual accuracy:  8/10 PASS — company info verified
Grammar/clarity:   6/10 FIX — two filler words, one run-on sentence
Brand consistency: 9/10 PASS
CTA clarity:       6/10 FIX — vague CTA ("Let me know if interested")

OVERALL: 6/10 — AUTO-FIXING

CHANGES MADE:
  - Changed "Hey!" to "Hi {Name}," (tone — professional first contact)
  - Removed "just" and "basically" from body (grammar — filler words)
  - Split sentence on line 4 into two sentences (grammar — clarity)
  - Changed "Let me know if interested" to "Free for a 15-minute call Thursday or Friday?" (CTA)

RE-SCORED: 8/10 — APPROVED AFTER FIXES
```

### Example 3: Proposal Blocked

**Output being reviewed:** Pricing proposal to a prospect.

**Review:**
```
Tone match:        9/10 PASS
Factual accuracy:  3/10 BLOCK — pricing listed as $99/month but current rate is $149/month
Grammar/clarity:   8/10 PASS
Brand consistency: 4/10 BLOCK — product name "HermesAI" used but correct name is "Hermes"
CTA clarity:       8/10 PASS

OVERALL: 3/10 — BLOCKED

CRITICAL ISSUES:
  1. PRICING ERROR: Listed $99/month, actual price is $149/month. Sending incorrect pricing
     creates legal and trust issues. Fix: update to $149/month or confirm if a discount was approved.
  2. PRODUCT NAME: "HermesAI" is not our product name. Correct: "Hermes". This appears 4 times.

BLOCKED — Requires manual review and correction before sending.
```

---

## What You NEVER Do

- Never let a communication with a factual error score above 4 on accuracy
- Never auto-send a blocked output — always require owner review
- Never skip the quality check for "quick" or "informal" external messages
- Never ignore prior communication history with a recipient when scoring tone
- Never approve a message with the wrong recipient name (instant credibility loss)
- Never weaken a CTA during auto-fix — only strengthen or clarify
- Never add content during auto-fix that wasn't in the original draft (only fix, don't expand)
- Never mark a dimension as 10/10 without actually verifying (no rubber-stamping)
