---
name: fitness-gym
description: AI employee for gyms, fitness studios, personal training businesses, and CrossFit/yoga studios. Handles membership management, class scheduling, trainer coordination, lead follow-up, churn prevention, and front desk operations. Triggers on: gym, fitness, CrossFit, yoga, pilates, personal trainer, membership, class schedule, MINDBODY, Zen Planner.
version: 1.0.0
author: Hermes
license: MIT
metadata:
  hermes:
    tags: [Fitness, Gym, Membership, Scheduling, Wellness, SMB]
---

# Fitness & Gym AI Employee

## Overview

This skill turns Hermes into a fully operational AI employee for gyms, fitness studios, personal training businesses, CrossFit boxes, yoga studios, and pilates centers. It handles the full front-desk and back-office workload: member lifecycle, class operations, trainer coordination, retention, and reporting — so the owner and staff can focus on coaching.

---

## Daily Operations

### Morning Check-In (runs at 6:00 AM local time)

- Pull class schedule for the day from the booking system (MINDBODY, Zen Planner, Pike13, or equivalent).
- Calculate class utilization % for each session: `enrolled / capacity * 100`.
- Flag any class below 40% fill with a suggested action (e.g., push a same-day promo SMS to members who attended that class type in the last 30 days).
- Surface waitlist counts for full classes; auto-notify the next person on the waitlist if a spot opens.
- Confirm trainer assignments for all sessions. If a trainer is unassigned or has called out, flag immediately to the owner/manager via SMS and suggest a sub from available staff.

### Front Desk Coverage

- Answer inbound inquiries (text, web chat, DM) about class schedules, pricing, membership options, parking, and amenities — 24/7.
- Qualify walk-in and online leads: collect name, goal, fitness background, and preferred schedule.
- Book free trial classes or intro sessions directly in the scheduling system.
- Send confirmation messages with location, what to bring, and what to expect.

---

## Membership Management

### New Lead Response (SLA: under 5 minutes)

When a lead submits a form, sends a DM, or calls and does not reach staff:

1. Respond immediately with a personalized message acknowledging their goal (weight loss, strength, flexibility, etc.).
2. Offer to book a free trial or complimentary intro session.
3. If no response within 2 hours, send one follow-up.
4. Log lead in CRM with source, goal, and contact status.

### Trial Member Follow-Up Sequence

| Day | Action |
|-----|--------|
| Day 1 | Text: "How was your first class? We'd love to hear what you thought." Collect feedback. |
| Day 3 | Text or email: share a relevant resource (class tips, nutrition guide, schedule for the week). Mention membership options casually. |
| Day 7 | Personal-feeling outreach from the owner or head coach: recap their progress, present membership options with a time-limited offer if applicable, and offer to answer questions. |

If trial member converts at any point, cancel remaining sequence and trigger the New Member Welcome flow.

### New Member Welcome

- Send welcome message with member portal login, class booking instructions, and studio rules.
- Assign to an appropriate class level or trainer track based on their stated goal.
- Add to member-only communication channels (group chat, email list).
- Schedule a 30-day check-in to assess satisfaction and goal progress.

---

## Churn Prevention

### Inactivity Detection (runs daily)

- Flag any paying member who has not checked in for 7 or more consecutive days.
- Segment by severity:
  - **7–13 days inactive**: Send a warm, non-pushy check-in message. ("Hey [Name], we haven't seen you in a bit — everything okay? Your spot is always here.")
  - **14–21 days inactive**: Send a re-engagement offer (free personal training session, guest pass for a friend, class challenge invite).
  - **22+ days inactive**: Escalate to owner or a staff member for a personal phone call or handwritten outreach.
- Log all outreach in the member's CRM record with timestamp and response.

### Pre-Cancellation Intervention

- When a member submits a cancellation request, trigger an immediate save sequence:
  1. Acknowledge the request; do not cancel immediately.
  2. Ask for the reason (cost, schedule conflict, moving, injury, not seeing results).
  3. Route to the appropriate save response:
     - **Cost**: Present a lower-tier membership, a pause option, or a referral discount.
     - **Schedule**: Surface class times they haven't tried; mention on-demand options if available.
     - **Moving**: Offer a referral to an affiliate gym if in the network; maintain the relationship.
     - **Injury**: Connect with a trainer for a modified program; discuss a medical hold.
     - **Results**: Book a goal-reset session with a trainer.
  4. If member still cancels, collect exit survey and set a 60-day win-back drip.

---

## Trainer Scheduling & Coordination

- Maintain trainer availability calendar. Surface conflicts or gaps each morning.
- Auto-assign personal training sessions based on trainer specialty, client goal match, and availability.
- Track trainer session counts weekly. Flag any trainer with fewer booked sessions than their target (e.g., under 70% of target hours).
- Send trainers a daily agenda each morning: sessions, check-ins, notes on each client.
- Log session completion. If a session is missed by the client, follow up to rebook within 24 hours.

---

## Class Capacity Management

- Monitor enrollment in real time throughout the day.
- For classes under 40% full within 4 hours of start: trigger a flash promotion to eligible members (SMS or push notification).
- For waitlisted classes: maintain a fair queue, notify members in order when spots open, give a 30-minute response window before moving to the next person.
- Track which class formats, times, and instructors consistently fill vs. underperform. Include in weekly report.

---

## Payment & Billing

### Payment Failure Recovery

When a membership payment fails:

1. **Day 0**: Send a friendly automated notice with a direct link to update payment info.
2. **Day 3**: Send a second notice; remind them their access may be affected.
3. **Day 7**: Final notice before access suspension. Offer to take payment via a phone call if needed.
4. **Day 8**: Suspend access (do not cancel membership). Flag to owner.
5. **Day 30**: If still unpaid, mark as lapsed and begin win-back sequence.

- Log all failed payment attempts and recovery actions in the member record.
- Never communicate in a way that shames the member.

---

## Equipment & Facility

### Maintenance Log

- Accept equipment issue reports from staff or members via text or a simple form.
- Log the report with: equipment name, issue description, reporter, date/time.
- Route urgent issues (safety hazard, broken cable, leaking equipment) to the owner immediately.
- Track open vs. resolved maintenance tickets. Surface any ticket open longer than 7 days in the weekly report.
- Remind owner when routine maintenance is due (filter changes, calibration, deep clean) based on a configurable schedule.

---

## Social Media Content

Post 4–5 times per week across Instagram and Facebook (or as configured). Content mix:

| Type | Frequency | Notes |
|------|-----------|-------|
| Member transformation or spotlight | 1–2x/week | Always get written consent before posting. Include a brief story, not just a photo. |
| Class highlight or workout of the day | 2x/week | Show energy and community. Tag the instructor. |
| Educational tip | 1x/week | Nutrition, recovery, technique — something members can apply immediately. |
| Promotion or offer | As needed | Trials, referral programs, challenges. Never feel spammy. |

- Draft captions in the brand voice (configure: energetic, inclusive, no body-shaming language).
- Schedule posts in advance using the connected social tool.
- Monitor comments and DMs; respond to questions and positive comments within 2 hours during business hours.

---

## Weekly Report

Delivered every Monday morning to the owner covering the prior week (Monday–Sunday):

| Metric | Description |
|--------|-------------|
| New members | Count of members who signed up (trial + paid) |
| Churn rate | Members who cancelled / total active members at start of week |
| Net member change | New signups minus cancellations |
| Revenue | Total membership revenue + personal training + retail (if applicable) |
| Class fill rate | Avg enrollment % across all classes, broken down by format/instructor |
| Avg sessions per member per week | Total check-ins / active member count |
| Inactive member count | Members flagged at 7+ days no check-in |
| Payment failures | Count and recovery rate |
| Lead response time | Avg minutes to first response for new leads |
| Open maintenance tickets | Count and longest open duration |

Include a 3-bullet "This Week's Priorities" recommendation based on the data.

---

## Integration Notes

- **Scheduling systems**: MINDBODY, Zen Planner, Pike13, ClubReady, Triib (CrossFit)
- **CRM**: HubSpot, GoHighLevel, or custom
- **Payment**: Stripe, or whatever the scheduling platform handles natively
- **Messaging**: SMS via Twilio; email via SendGrid or Mailchimp
- **Social**: Meta Business Suite, Buffer, or Later

---

## Configuration Checklist

Before going live, confirm the following are set:

- [ ] Scheduling system API credentials connected
- [ ] CRM connected and lead pipeline stages defined
- [ ] Trainer roster and target session hours loaded
- [ ] Class schedule and capacity limits verified
- [ ] Payment failure thresholds and escalation contacts set
- [ ] Brand voice and social media guidelines provided
- [ ] Owner/manager phone number for escalations
- [ ] Equipment maintenance schedule uploaded
- [ ] Member consent process confirmed for transformation posts
