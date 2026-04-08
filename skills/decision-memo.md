# Decision Memo / Recommendation

## When to Use

Activate this skill when:
- User says "I need to decide", "what should I do about", "help me think through"
- User says "give me options for", "pros and cons of", "should I X or Y"
- User says "write a decision memo", "recommendation on", "analyze this decision"
- A downstream skill surfaces a decision point (e.g., follow-up engine finds a stalled deal needing a strategic call)
- Owner is weighing a hire, a pricing change, a partnership, a vendor choice, a feature prioritization
- Any situation where there are multiple paths forward and meaningful tradeoffs

## What You Need

### Tools
- `web_search` — Research market data, competitor moves, pricing benchmarks, industry trends
- `browser_navigate` — Pull detailed pages: competitor pricing, case studies, analyst reports
- `prospect_tool` — CRM data for customer-facing decisions (deal size, history, churn risk)
- `email_read` — Pull relevant threads, past discussions, stakeholder opinions
- `state_db` — Retrieve past decisions on similar topics, historical outcomes
- `file_tools` — Save memo as structured document for future reference
- `send_message` — Deliver memo to owner via Telegram
- `email_send` — Send memo to stakeholders if needed

### Data Needed
- Clear problem statement (what decision needs to be made)
- Context: why now, what triggered this, what happens if we do nothing
- Constraints: budget, timeline, team capacity, contractual obligations
- Stakeholders: who's affected, who has veto power, who needs to be consulted
- Past decisions: have we faced this before, what did we do, how did it turn out

## Process

### Step 1: Frame the Decision

Before generating options, get crystal clear on what's actually being decided.

```
1. Identify the core question:
   - Strip away symptoms to find the real decision
   - "Should I hire a VA?" might really be "How do I get 10 hours/week back?"
   - "Should I switch CRMs?" might really be "Why are deals falling through cracks?"

2. Define the decision type:
   TYPE A — Reversible (can undo cheaply): Bias toward speed, pick and move
   TYPE B — Irreversible (hard/expensive to undo): Bias toward thoroughness

3. Set the decision timeframe:
   - When does this need to be decided by?
   - What's the cost of waiting another week?
   - Is there an event forcing the decision (contract expiry, deadline, competitor move)?

4. Identify who's affected:
   - Direct stakeholders (team, customers, investors)
   - Indirect stakeholders (partners, vendors, future hires)
```

### Step 2: Gather Evidence

Research to inform the options — don't generate options in a vacuum.

```
1. Internal data:
   prospect_tool(action="search", query=relevant_customers)
   email_read(search=topic_keywords, limit=20)
   state_db(action="get_similar_decisions", topic=decision_topic)
   → What do our numbers say? What have stakeholders expressed?

2. External data:
   web_search(query=f"{decision_topic} best practices {industry}")
   web_search(query=f"{decision_topic} case study {similar_company_size}")
   browser_navigate(url=competitor_pricing_or_feature_page)
   → What are others doing? What does the market say?

3. Historical context:
   state_db(action="get_past_decisions", category=decision_category)
   → Have we decided this before? What was the outcome?
   → If yes, what's changed since then?
```

### Step 3: Generate Options

Always produce exactly 3 options. Not 2 (false dichotomy), not 5 (analysis paralysis).

```
OPTION GENERATION RULES:
  1. Option A: The conservative/safe path (low risk, moderate reward)
  2. Option B: The bold/aggressive path (higher risk, higher reward)
  3. Option C: The creative/unexpected path (reframe the problem)

  NEVER include "do nothing" as a standalone option.
  Instead, if inaction is viable, make it Option A with explicit consequences.

  Each option MUST include:
  - What: Concrete description of what happens
  - Cost: Money, time, opportunity cost
  - Timeline: How long to implement and see results
  - Risk: What could go wrong, likelihood, severity
  - Upside: Best-case outcome
  - Dependency: What needs to be true for this to work
```

### Step 4: Analyze Tradeoffs

For each option, run a structured analysis.

```
TRADEOFF MATRIX:
                    Option A        Option B        Option C
  Cost              $X              $Y              $Z
  Timeline          N weeks         N weeks         N weeks
  Risk level        Low/Med/High    Low/Med/High    Low/Med/High
  Reversibility     Easy/Hard       Easy/Hard       Easy/Hard
  Team impact       Minimal/Major   Minimal/Major   Minimal/Major
  Customer impact   None/Some/Major None/Some/Major None/Some/Major
  Upside potential  $X or %         $X or %         $X or %

SECOND-ORDER EFFECTS:
  For each option, ask:
  - If we do this, what becomes easier in 6 months?
  - If we do this, what becomes harder in 6 months?
  - What does this signal to customers/team/investors?
  - Does this create or close future options?
```

### Step 5: Make a Recommendation

Take a clear stance. The owner wants your opinion, not just a spreadsheet.

```
RECOMMENDATION FRAMEWORK:
  1. State your pick: "I recommend Option [X]"
  2. Give the primary reason (one sentence)
  3. Acknowledge what you're giving up (main tradeoff)
  4. State the key assumption that must be true
  5. Define the trigger to revisit (when to reconsider)

RECOMMENDATION STRENGTH:
  STRONG: "I'm confident. The data clearly supports this."
  MODERATE: "This is the best option given what we know, but [uncertainty]."
  WEAK: "This is a coin flip. Here's my lean and why."

  Always disclose your confidence level.
```

### Step 6: Define Next Steps

Every memo ends with concrete actions.

```
NEXT STEPS (always include):
  1. Immediate action: What to do in the next 24 hours
  2. Who to tell: Which stakeholders need to know
  3. What to measure: How we'll know if this was the right call
  4. Review date: When to check back on the decision
  5. Reversal trigger: What signal means we should change course
```

### Step 7: Deliver and Log

```
1. Format the memo (see Output Format below)

2. Deliver to owner:
   send_message(chat_id=owner_id, text=memo_summary)
   For complex decisions: email_send(to=owner, subject=f"Decision Memo: {topic}", body=full_memo)

3. Log the decision:
   state_db(action="log_decision", data={
     topic: decision_topic,
     options_considered: [A, B, C],
     recommendation: chosen_option,
     confidence: "strong/moderate/weak",
     decision_date: today,
     review_date: review_date,
     outcome: "pending"
   })

4. Set follow-up:
   state_db(action="create_followup", date=review_date,
     message=f"Review decision: {topic}. Is the outcome matching expectations?")
```

## Output Format

### Full Decision Memo

```
DECISION MEMO: {Title}
Date: {date}
Requested by: {owner}
Decision needed by: {deadline}
Type: {Reversible / Irreversible}
============================================

SITUATION
  {2-3 sentence summary of the context and why this decision matters now.
   Include the triggering event and cost of inaction.}

OPTION A: {Name} (Conservative)
  What: {Description}
  Cost: {$X / N hours / opportunity cost}
  Timeline: {N weeks to implement, N weeks to see results}
  Risk: {What could go wrong}
  Upside: {Best case outcome}
  Key dependency: {What must be true}

OPTION B: {Name} (Aggressive)
  What: {Description}
  Cost: {$X / N hours / opportunity cost}
  Timeline: {N weeks to implement, N weeks to see results}
  Risk: {What could go wrong}
  Upside: {Best case outcome}
  Key dependency: {What must be true}

OPTION C: {Name} (Creative)
  What: {Description}
  Cost: {$X / N hours / opportunity cost}
  Timeline: {N weeks to implement, N weeks to see results}
  Risk: {What could go wrong}
  Upside: {Best case outcome}
  Key dependency: {What must be true}

TRADEOFF MATRIX
                    Option A        Option B        Option C
  Cost              ...             ...             ...
  Timeline          ...             ...             ...
  Risk              ...             ...             ...
  Reversibility     ...             ...             ...
  Upside            ...             ...             ...

RECOMMENDATION
  I recommend Option {X}. {Primary reason in one sentence.}

  Confidence: {Strong / Moderate / Weak}

  This means we're accepting {main tradeoff} in exchange for {main benefit}.
  This works if {key assumption}. If {reversal trigger}, we should reconsider.

NEXT STEPS
  1. {Immediate action — today}
  2. {Tell stakeholder X — this week}
  3. {Measure Y — starting on date}
  4. {Review this decision on date}
```

### Quick Decision (for simple/reversible choices)

```
QUICK DECISION: {Title}

You asked: {question}
My take: {Option} because {one-line reason}.
Risk if wrong: {low/reversible}. Cost to try: {low}.
Do it. Move on. Revisit in {N days} if it's not working.
```

## Examples

### Example 1: Pricing Decision

**Input:** "Should I raise prices? Some customers are complaining but we're undercharging."

**Process:**
1. Pull CRM data: customer tiers, revenue distribution, churn history
2. Web search: SaaS pricing benchmarks, competitor pricing
3. Email scan: customer complaint threads, pricing objections

**Output:**
```
DECISION MEMO: Pricing Restructure

SITUATION
  Current pricing ($49/mo) is 40% below market average ($82/mo) for
  similar features. Three customers complained about recent $10 increase,
  but churn remained at 2.1% (healthy). Underpricing is leaving ~$180K/yr
  on the table and attracting low-value customers.

OPTION A: Grandfather + Raise New (Conservative)
  Existing customers keep current price. New customers pay $79/mo.
  Cost: $0. Timeline: Immediate. Risk: Creates pricing complexity.
  Upside: Zero churn risk from existing base.

OPTION B: Universal Raise to $79/mo (Aggressive)
  30-day notice to all customers. Move everyone to new pricing.
  Cost: Potential 5-8% churn. Timeline: 30 days. Risk: Lose some customers.
  Upside: $180K/yr additional revenue. Simpler pricing.

OPTION C: Value-Based Tiers (Creative)
  Keep $49 for basic, add $99 Pro tier with premium features.
  Cost: 2 weeks dev for feature gating. Timeline: 6 weeks.
  Risk: Complexity. Upside: Captures both segments, upsell path.

RECOMMENDATION
  I recommend Option C. It captures the revenue without punishing loyal
  customers, and creates a natural upsell path.

  Confidence: Moderate — depends on whether Pro features justify the gap.
  Revisit in 60 days if <10% of base upgrades to Pro.
```

### Example 2: Quick Hire Decision

**Input:** "Should I hire a contractor or full-time for this marketing role?"

**Output:**
```
QUICK DECISION: Marketing Hire — Contractor vs Full-Time

You asked: Contractor or full-time?
My take: Contractor (3-month trial) because you haven't validated
  the marketing channel yet. Hiring full-time before product-market
  fit for this channel = $80K+ risk if the channel doesn't work.
Risk if wrong: Low. Convert to full-time if results are good.
Cost to try: ~$15K for 3 months.
Do it. Move on. Revisit at 90 days with performance data.
```

### Example 3: Strategic Partnership

**Input:** "Company X wants to integrate with us. They're a competitor but it could expand our market."

**Process:**
1. Research Company X: size, market position, recent moves, reputation
2. Check CRM: any shared customers, competitive losses to them
3. Analyze: what do they gain vs what do we gain
4. Model: revenue impact, risk of them copying our features

**Output:** Full decision memo with partnership terms analysis, IP risk assessment, and revenue projections across all three options.
