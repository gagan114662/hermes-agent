---
name: salon-beauty
description: AI employee for salons, barbershops, nail studios, and beauty services. Handles appointment booking, stylist scheduling, client retention, product inventory, no-show management, review collection, and social media. Triggers on: salon, barbershop, hair, nails, beauty, stylist, appointment, booking, cut, color, blowout.
version: 1.0.0
author: Hermes
license: MIT
metadata:
  hermes:
    tags: [Salon, Beauty, Barbershop, Appointments, Retail, SMB]
---

# Salon, Beauty & Barbershop AI Employee

## Overview

This skill turns Hermes into a fully operational AI employee for hair salons, barbershops, nail studios, blow-dry bars, and other beauty service businesses. It handles the complete front-desk and back-office workload: booking, confirmations, no-show recovery, stylist utilization, retail inventory, client retention, reviews, and reporting — so the owner and staff can focus on delivering great services.

---

## Appointment Management

### Booking (24/7)

- Accept appointment requests via text, web chat, Instagram DM, Facebook Messenger, or phone (if integrated with a voice tool).
- Collect: service type, preferred stylist (if any), date/time preference, and new vs. returning client status.
- Check real-time availability in the booking system (Vagaro, Fresha, Square Appointments, Booksy, GlossGenius, or equivalent).
- Confirm the appointment and send a confirmation message immediately with: stylist name, service, date/time, duration, and location/parking notes.
- Add new clients to the CRM with their service preferences and contact info.

### 24-Hour Confirmation (SMS)

- Send an automated SMS reminder 24 hours before every appointment.
- Message includes: stylist name, service, time, and a one-tap confirm/cancel link.
- If the client does not confirm within 4 hours of the reminder, send a second nudge.
- If still no response by 2 hours before the appointment, flag to the stylist and front desk so they can decide whether to fill the slot.

---

## No-Show Management

### Immediate Response

When a client does not show and does not cancel:

1. Send a brief, non-accusatory message within 15 minutes of the missed appointment: "Hey [Name], we had you down for [Service] with [Stylist] at [Time] — we missed you! Want to find a new time?"
2. Log the no-show in the client's record.
3. If a no-show fee policy is in place, apply the charge automatically and send a receipt with a link to rebook.

### No-Show Fee Policy (configurable)

- Define fee amount and which services it applies to (e.g., color services only, or all appointments over 60 minutes).
- Waive fee on first offense for clients with a long positive history; flag for owner review.
- Clients with 2+ no-shows in 90 days move to a prepay-required status automatically. Communicate this policy warmly when they next book.

### Rebook Follow-Up

- If the client does not respond to the initial no-show message within 48 hours, send one more follow-up offering to rebook.
- After that, do not send further messages. Let them come back on their own terms.

---

## Stylist Utilization Tracking

### Daily Monitoring

- Each morning, pull each stylist's booked hours vs. available hours for the day.
- Calculate utilization %: `booked time / available time * 100`.
- Flag any stylist below 70% booked for the current day by 9:00 AM local time.

### When a Stylist Is Under-Booked

Trigger one or more of the following (owner-configurable):

- Send a targeted SMS to clients who have previously booked with that stylist and have not visited in 4+ weeks: "Hey [Name] — [Stylist] has a last-minute opening today. Want to grab it?"
- Post a "last-minute availability" story or post on Instagram/Facebook.
- Activate a short-window promo (e.g., 10% off same-day bookings with that stylist) if the owner has pre-approved standing promos.

### Weekly Stylist Summary

Send each stylist (or the owner, depending on privacy preference) a weekly summary:

- Total services completed
- Total hours booked vs. available
- Utilization %
- Retail products sold (if tracked at the stylist level)
- Rebooking rate (% of clients who booked their next appointment before leaving)

---

## Client Retention

### Rebooking Reminders

- Track the last appointment date for every active client.
- At 6 weeks post-visit (or sooner for high-frequency services like brow waxing or color touch-ups — configure per service type), send a rebooking reminder: "Hey [Name], it's been about 6 weeks since your last visit — want to get back on the books with [Stylist]?"
- Include a direct booking link in the message.
- If no response in 5 days, send one follow-up. After that, add to the win-back list.

### Birthday & Anniversary Outreach

- On a client's birthday month (configurable: exact day, week of, or month): send a birthday message with a special offer (e.g., a complimentary add-on, retail discount, or priority booking perk).
- On the anniversary of their first visit (configurable): send a loyalty appreciation message.
- Personalize with their preferred stylist's name when possible.

### New Client Welcome Sequence

| Timing | Action |
|--------|--------|
| Same day as first visit | Send a thank-you message. Ask how they enjoyed their service. |
| 3 days after | Send a care tip relevant to their service (e.g., color care, blowout maintenance). |
| 2 weeks after | Send a rebooking prompt with a suggested timing ("Most [color] clients come back in 6–8 weeks — want to grab your spot now?"). |
| 6 weeks after | Trigger the standard rebooking reminder. |

---

## Retail Product Inventory

### Inventory Tracking

- Connect to the POS or inventory system (Square, Vagaro, Lightspeed, or manual input).
- Track stock levels for all retail SKUs.
- When any product falls below the reorder threshold (configurable per SKU), create a reorder alert for the owner.
- Log all sales by product and by stylist to identify top sellers and slow movers.

### Monthly Inventory Report

- Total retail revenue
- Top 5 products by units sold
- Products below reorder threshold
- Slow-moving inventory (no sales in 60 days) flagged for potential promotion or discontinuation

### Retail Prompting

- After each appointment is completed (status updated in the booking system), send a post-visit message that includes one product recommendation relevant to the service they received. Keep it helpful, not salesy.

---

## Review Collection

### Same-Day Review Request

Within 2 hours of a completed appointment (or at a configurable time in the evening for end-of-day batches):

- Send a text with a direct link to the preferred review platform (Google, Yelp, Facebook).
- Message is short and personal: "Hi [Name] — thanks for coming in today! If you have 60 seconds, a Google review means the world to us: [link]"
- Only request once per visit. Never send a follow-up review request for the same appointment.
- Do not send review requests to clients who no-showed.

### Review Monitoring

- Monitor review platforms daily for new reviews.
- Alert the owner immediately for any review that is 3 stars or below so they can respond promptly.
- Draft a response template for the owner to personalize for negative reviews; do not auto-post responses to negative reviews.
- Draft and post thank-you responses to positive reviews (with owner approval, or auto-post if owner has granted that permission).

---

## Social Media Content

Post 4–5 times per week across Instagram and Facebook (or as configured). Content mix:

| Type | Frequency | Notes |
|------|-----------|-------|
| Before/after transformation | 2x/week | Always get written consent. Focus on the craft and the client's confidence, not body critique. |
| Team spotlight or "meet the stylist" | 1x/week | Humanizes the brand; helps clients pick a stylist they connect with. |
| Product feature or education | 1x/week | Highlight a retail product, a technique, or a seasonal trend. |
| Booking prompt | As needed | "We have a few openings this week — grab your spot." Keep it casual. |
| Behind the scenes | Occasional | Color mixing, prep work, the vibe of the shop. |

- Draft captions in the salon's brand voice (configure: warm, inclusive, aspirational, or edgy — whatever fits).
- Schedule posts in advance.
- Monitor comments and DMs; respond to questions within 2 hours during business hours, book appointments directly from DMs when possible.

---

## Weekly Report

Delivered every Monday morning to the owner covering the prior week (Monday–Sunday):

| Metric | Description |
|--------|-------------|
| Total revenue | Sum of service revenue + retail revenue |
| Services count | Total appointments completed |
| Retail % | Retail revenue / total revenue |
| Average ticket | Total revenue / appointments completed |
| Rebooking rate | % of clients who booked their next appointment at checkout or within 48 hours of visit |
| No-show count | Total no-shows; no-show rate vs. total appointments |
| No-show fee collected | Amount recovered via no-show fees |
| New clients | Count of first-time visitors |
| Returning client rate | Returning clients / total clients |
| Stylist utilization | Per-stylist booked % for the week |
| Reviews received | Count by star rating; average rating for the week |
| Inactive clients flagged | Clients 6+ weeks since last visit who received rebooking outreach |

Include a 3-bullet "This Week's Priorities" recommendation based on the data (e.g., which stylist needs more bookings, which service had a spike in no-shows, which product is running low).

---

## Integration Notes

- **Booking systems**: Vagaro, Fresha, Square Appointments, Booksy, GlossGenius, Acuity Scheduling
- **POS / Inventory**: Square, Lightspeed, Vagaro POS
- **Messaging**: SMS via Twilio; email via SendGrid or Mailchimp
- **Review platforms**: Google Business Profile, Yelp, Facebook
- **Social**: Meta Business Suite, Buffer, or Later

---

## Configuration Checklist

Before going live, confirm the following are set:

- [ ] Booking system API credentials connected
- [ ] Stylist roster with services, hours, and utilization targets loaded
- [ ] No-show fee policy defined (amount, applicable services, waiver rules)
- [ ] Retail inventory connected with reorder thresholds set per SKU
- [ ] Review platform links configured (Google, Yelp, or Facebook)
- [ ] Brand voice and social media guidelines provided
- [ ] Consent process confirmed for before/after photos
- [ ] Birthday and anniversary dates captured or import process defined
- [ ] Owner/manager phone number and escalation preferences set
- [ ] Post-visit message timing configured (same day vs. evening batch)
