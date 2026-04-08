---
name: business-vertical-auto-detect
description: Automatically detects what type of business the owner runs by reading signals from their computer — installed apps, file names, email domains, browser tabs, calendar events. Then loads the appropriate vertical skill and configures Hermes accordingly. Run this skill once at first install, then re-run if the business type seems wrong.
version: 1.0.0
author: Hermes
license: MIT
metadata:
  hermes:
    tags: [Onboarding, Auto-Detection, Business Intelligence, Setup]
---

# Business Vertical Auto-Detection

Run this at first install to automatically identify the business type and load the right operational playbook.

## Detection Signals

Hermes reads these signals (already accessible via granted permissions) to infer business type:

### App & Software Signals
| Signal | Likely Vertical |
|---|---|
| Dentrix, Eaglesoft, Open Dental, Carestream | Dental Practice |
| Athenahealth, eClinicalWorks, Kareo, Practice Fusion | Medical Practice |
| Toast, Square for Restaurants, Aloha, Lightspeed Restaurant | Restaurant |
| MINDBODY, Zen Planner, Pike13, Wodify | Fitness / Gym |
| Salon Iris, Vagaro, Fresha, Boulevard | Salon / Beauty |
| Clio, MyCase, PracticePanther, Filevine | Law Firm |
| QuickBooks (with "clients" folder), Xero + multiple entities | Accounting Firm |
| Buildxact, Procore, CoConstruct, Buildertrend | Construction |
| Shopify, WooCommerce, Gorgias, ShipStation | E-commerce |
| AppFolio, Buildium, Propertyware, Rent Manager | Property Management |
| HubSpot + multiple client folders, Agency Analytics | Marketing Agency |
| MLS access, DocuSign + "purchase agreement" files | Real Estate |
| Lightspeed Retail, Shopify POS, Vend | Retail |

### File & Folder Name Signals
- Folders named "Patients", "Charts", "X-rays" → Healthcare (Dental/Medical)
- Files with "CDT", "CPT", "ICD" codes → Healthcare billing
- Folders named "Properties", "Listings", "MLS" → Real Estate / Property Mgmt
- Files with "SOW", "Change Order", "Permit" → Construction
- Folders named "Clients", "Retainer", "Matter" → Law Firm
- Files with "Inventory", "PO", "SKU", "UPC" → Retail / E-commerce
- Folders named "Campaigns", "Ad Spend", "Creative" → Marketing Agency

### Email Domain Signals
- Emails from insurance companies (insurance.com, bcbs.*, cigna.*, aetna.*) → Healthcare
- Emails from real estate portals (zillow.com, mls.*, har.*, nwmls.*) → Real Estate
- Emails from food distributors (sysco.com, usfood.com, pfgc.com) → Restaurant
- Emails from legal research (westlaw.com, lexisnexis.com) → Law Firm
- Emails from shipping carriers (fedex.com, ups.com, shipbob.com) → E-commerce

### Calendar Event Signals
- Events with "patient", "appointment", "Dr." → Healthcare
- Events with "showing", "closing", "open house" → Real Estate
- Events with "deposition", "hearing", "client meeting" → Law Firm
- Events with "pour", "framing", "inspection", "walkthrough" → Construction

## Detection Algorithm

```
1. Scan installed applications (check /Applications and ~/Applications)
2. Read app names → match against App Signal table above
3. Scan file system for folder/file name patterns (top 3 directory levels only)
4. Sample recent emails (subject lines only, no body) → match domain patterns
5. Read calendar event titles from next 30 days → match patterns

Score each vertical: 1 point per signal match
Vertical with score ≥ 3 → HIGH CONFIDENCE → auto-configure
Vertical with score = 1-2 → MEDIUM CONFIDENCE → confirm with owner
No match → ask owner directly via Telegram: "What type of business do you run?"
```

## Multi-Vertical Detection

Some businesses span multiple verticals:
- Medical Spa = Med Spa (primary) + Medical Practice signals
- Dental + Ortho = Dental (primary)
- Real Estate Investor + Property Mgmt = Property Management (primary)

If 2+ verticals each score ≥ 3: ask owner to confirm primary.

## Auto-Configuration Actions

Once vertical is confirmed:

1. **Load vertical skill** — activate the matching SKILL.md from `skills/business-verticals/`
2. **Set context variables**:
   - `business_type`: detected vertical
   - `primary_software`: detected practice management system
   - `owner_name`: from Contacts/email signature
   - `business_name`: from email signature / business cards / Keychain
3. **Send Telegram confirmation**:
   > "I detected you run a [vertical] business using [software]. I've loaded the [vertical] playbook and I'm ready to start working. I'll send you a full status in 5 minutes."
4. **Run first-pass queue** — immediately execute the vertical's daily morning checklist

## Re-Detection

Run again if:
- Business type seems wrong (owner corrects Hermes)
- New software detected that contradicts current vertical
- Owner installs new practice management system

Command: owner texts Hermes "re-detect my business" → runs full detection again

## What You NEVER Do
- Never assume healthcare vertical without explicit software or file signals (HIPAA stakes are high)
- Never access medical record files during detection — only folder names and app names
- Never re-configure a confirmed vertical without owner confirmation
