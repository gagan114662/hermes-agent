#!/usr/bin/env python3
"""
Website Business Profile Analyzer

Crawls a user's business website and builds a rich business profile, including:
- Company metadata (name, industry, description)
- Services and offerings
- Competitor intelligence (via Exa)
- Social media presence
- Contact information
- Estimated team size and pain points
- Recommended employee roles

Usage:
    python scripts/website_analyzer.py https://example.com
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Industry -> recommended_employees mapping
INDUSTRY_ROLE_MAPPING = {
    "restaurant": ["reservations_manager", "review_responder", "social_media_manager", "menu_updater"],
    "saas": ["customer_support", "docs_writer", "lead_qualifier", "onboarding_specialist"],
    "salon": ["appointment_scheduler", "review_responder", "social_media_manager", "loyalty_manager"],
    "law_firm": ["intake_coordinator", "document_drafter", "client_communicator", "billing_assistant"],
    "ecommerce": ["inventory_monitor", "customer_support", "social_media_manager", "review_responder"],
    "agency": ["project_coordinator", "client_communicator", "content_creator", "lead_qualifier"],
    "healthcare": ["appointment_scheduler", "patient_communicator", "billing_assistant", "review_responder"],
    "real_estate": ["lead_qualifier", "listing_manager", "client_communicator", "social_media_manager"],
    "fitness": ["class_scheduler", "member_communicator", "social_media_manager", "review_responder"],
    "education": ["enrollment_coordinator", "student_communicator", "content_creator", "scheduling_assistant"],
}


@dataclass
class BusinessProfile:
    """Structured business profile extracted from website and research."""
    business_name: str
    website_url: str
    industry: str
    description: str
    services: List[str] = field(default_factory=list)
    target_customer: str = ""
    tone: str = "professional"
    competitors: List[str] = field(default_factory=list)
    team_size_estimate: str = "small"
    social_media: Dict[str, str] = field(default_factory=dict)
    contact_info: Dict[str, str] = field(default_factory=dict)
    pain_points: List[str] = field(default_factory=list)
    recommended_employees: List[str] = field(default_factory=list)


def _get_exa_client():
    """Lazy-load and return the Exa client."""
    from exa_py import Exa
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        logger.warning("EXA_API_KEY not set. Competitor search will be skipped.")
        return None
    return Exa(api_key=api_key)


async def _fetch_website_content(url: str) -> str:
    """Fetch website content using simple requests (fallback to firecrawl if available)."""
    try:
        import requests
        logger.info(f"Fetching {url}...")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.warning(f"Failed to fetch {url} with requests: {e}")

        # Fallback to firecrawl if available
        try:
            import firecrawl
            api_key = os.getenv("FIRECRAWL_API_KEY")
            if not api_key:
                logger.warning("FIRECRAWL_API_KEY not set. Cannot fallback to firecrawl.")
                return ""

            app = firecrawl.FirecrawlApp(api_key=api_key)
            result = app.scrape_url(url, {"formats": ["markdown"]})
            return result.get("markdown", "")
        except Exception as e2:
            logger.warning(f"Firecrawl also failed: {e2}")
            return ""


def _extract_social_links(content: str) -> Dict[str, str]:
    """Extract social media URLs from website content."""
    social_platforms = {
        "linkedin": r"https?://(?:www\.)?linkedin\.com/(?:company|in)/[\w\-]+",
        "twitter": r"https?://(?:www\.)?(?:twitter|x)\.com/[\w\-]+",
        "facebook": r"https?://(?:www\.)?facebook\.com/[\w\-\.]+",
        "instagram": r"https?://(?:www\.)?instagram\.com/[\w\.]+",
        "youtube": r"https?://(?:www\.)?youtube\.com/(?:channel|c|user)/[\w\-]+",
        "github": r"https?://(?:www\.)?github\.com/[\w\-]+",
    }

    social_media = {}
    for platform, pattern in social_platforms.items():
        matches = re.findall(pattern, content)
        if matches:
            # Take the first match for each platform
            social_media[platform] = matches[0]

    return social_media


def _extract_contact_info(content: str) -> Dict[str, str]:
    """Extract email and phone from website content."""
    contact_info = {}

    # Extract email (simple pattern)
    email_pattern = r"[\w\.-]+@[\w\.-]+\.\w+"
    emails = re.findall(email_pattern, content)
    if emails:
        # Prefer non-noreply emails
        for email in emails:
            if "noreply" not in email.lower():
                contact_info["email"] = email
                break
        if "email" not in contact_info:
            contact_info["email"] = emails[0]

    # Extract phone (simple US pattern)
    phone_pattern = r"\(?(\d{3})\)?[\s\-.]?(\d{3})[\s\-.]?(\d{4})"
    phones = re.findall(phone_pattern, content)
    if phones:
        contact_info["phone"] = f"({phones[0][0]}) {phones[0][1]}-{phones[0][2]}"

    return contact_info


async def _analyze_with_llm(
    website_content: str,
    business_name: str,
    website_url: str
) -> Dict[str, Any]:
    """Analyze website content using Claude to extract business insights."""
    try:
        # Lazy import of auxiliary client
        from agent.auxiliary_client import async_call_llm, extract_content_or_reasoning
    except ImportError:
        logger.warning("auxiliary_client not available. Using rule-based analysis.")
        return _rule_based_analysis(website_content, business_name)

    # Prepare a comprehensive analysis prompt
    prompt = f"""Analyze this business website content and extract structured information about their business.

Business Name: {business_name}
Website URL: {website_url}

Website Content (first 2000 chars):
{website_content[:2000]}

Extract and provide JSON with these fields:
- industry: One of ["restaurant", "saas", "salon", "law_firm", "ecommerce", "agency", "healthcare", "real_estate", "fitness", "education", "other"]
- description: 1-2 sentences about what they do
- services: List of services/products they offer (5-8 items)
- target_customer: Who they serve (1 sentence)
- tone: professional/friendly/casual
- team_size_estimate: small/medium/large
- pain_points: List of 3-4 likely business challenges

Return ONLY valid JSON, no markdown or extra text."""

    try:
        result = await async_call_llm(prompt, model="auto", max_tokens=1500)
        analysis_text = extract_content_or_reasoning(result)

        # Parse the JSON response
        json_match = re.search(r"\{.*\}", analysis_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
    except Exception as e:
        logger.warning(f"LLM analysis failed: {e}. Falling back to rule-based analysis.")

    return _rule_based_analysis(website_content, business_name)


def _rule_based_analysis(content: str, business_name: str) -> Dict[str, Any]:
    """
    Rule-based fallback analysis when LLM is unavailable.
    Uses keyword matching and heuristics to infer business characteristics.
    """
    content_lower = content.lower()

    # Industry detection via keywords
    industry_keywords = {
        "restaurant": ["restaurant", "cafe", "diner", "bistro", "menu", "cuisine", "dining"],
        "saas": ["software", "cloud", "api", "subscription", "dashboard", "platform", "app"],
        "salon": ["salon", "haircut", "beauty", "spa", "stylist", "appointment"],
        "law_firm": ["attorney", "lawyer", "legal", "law firm", "esq", "litigation"],
        "ecommerce": ["shop", "store", "buy now", "add to cart", "checkout", "product"],
        "agency": ["agency", "creative", "design", "marketing", "campaign", "branding"],
        "healthcare": ["doctor", "clinic", "hospital", "medical", "patient", "appointment"],
        "real_estate": ["real estate", "property", "listing", "realtor", "home", "apartment"],
        "fitness": ["gym", "fitness", "trainer", "class", "workout", "membership"],
        "education": ["course", "school", "university", "student", "learning", "tuition"],
    }

    detected_industry = "other"
    max_matches = 0
    for industry, keywords in industry_keywords.items():
        matches = sum(1 for kw in keywords if kw in content_lower)
        if matches > max_matches:
            max_matches = matches
            detected_industry = industry

    # Estimate tone from content
    casual_words = ["hey", "cool", "awesome", "fun", "love", "excited"]
    casual_count = sum(1 for word in casual_words if word in content_lower)
    tone = "casual" if casual_count > 3 else ("friendly" if casual_count > 0 else "professional")

    # Estimate team size (heuristic based on content length and structure complexity)
    content_length = len(content)
    team_size = "large" if content_length > 50000 else ("medium" if content_length > 10000 else "small")

    return {
        "industry": detected_industry,
        "description": f"Business in the {detected_industry} industry.",
        "services": _extract_services_heuristic(content),
        "target_customer": "Customers seeking their services",
        "tone": tone,
        "team_size_estimate": team_size,
        "pain_points": _get_pain_points_for_industry(detected_industry),
    }


def _extract_services_heuristic(content: str) -> List[str]:
    """Extract likely services from content using keyword patterns."""
    services = []

    # Look for common service-indicating patterns
    patterns = [
        r"(?:we (?:offer|provide|specialize in|deliver).*?)[\"']([^\"']+)[\"']",
        r"(?:our (?:services|products).*?):([^\n\.]+)",
        r"(?:includes?|such as).*?(?:and|,).*?(?:and|\.)",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        services.extend([m.strip() for m in matches if m.strip()])

    # Remove duplicates and limit to 5-8 items
    services = list(dict.fromkeys(services))[:8]

    # If we didn't find much, use generic fallback based on content snippets
    if not services:
        sentences = re.split(r"[.!?]", content)
        for sent in sentences:
            if any(word in sent.lower() for word in ["service", "solution", "product", "offer"]):
                services.append(sent.strip()[:100])
                if len(services) >= 3:
                    break

    return services[:8]


def _get_pain_points_for_industry(industry: str) -> List[str]:
    """Return common pain points for an industry."""
    pain_point_map = {
        "restaurant": ["table management", "staff scheduling", "customer reviews", "inventory tracking"],
        "saas": ["user onboarding", "customer retention", "feature feedback", "support tickets"],
        "salon": ["appointment booking", "staff coordination", "inventory of products", "customer retention"],
        "law_firm": ["client intake", "document management", "billing accuracy", "time tracking"],
        "ecommerce": ["inventory management", "customer support volume", "return processing", "conversion rate"],
        "agency": ["project coordination", "resource allocation", "client communication", "proposal generation"],
        "healthcare": ["appointment scheduling", "patient communication", "billing compliance", "record management"],
        "real_estate": ["lead management", "property showings", "contract processing", "market analysis"],
        "fitness": ["class scheduling", "member retention", "billing automation", "engagement"],
        "education": ["enrollment management", "student communication", "curriculum delivery", "progress tracking"],
    }
    return pain_point_map.get(industry, ["lead generation", "customer support", "operational efficiency", "marketing"])


async def _search_competitors(business_name: str, industry: str) -> List[str]:
    """Search for competitors using Exa."""
    exa_client = _get_exa_client()
    if not exa_client:
        return []

    try:
        # Construct a search query for competitors
        query = f"{industry} companies similar to {business_name}"
        logger.info(f"Searching for competitors: {query}")

        # Use Exa to search for competitor information
        results = exa_client.search(query, num_results=5)

        # Extract company names from results
        competitors = []
        for result in results.results:
            # Try to extract company name from title or URL
            title = result.title or ""
            url = result.url or ""

            if title and title != business_name:
                competitors.append(title.split(" | ")[0][:50])

        return competitors[:5]
    except Exception as e:
        logger.warning(f"Competitor search failed: {e}")
        return []


async def analyze_website(website_url: str) -> BusinessProfile:
    """
    Main function to analyze a business website and create a profile.

    Args:
        website_url: The business website URL to analyze

    Returns:
        BusinessProfile with extracted information
    """
    # Validate and normalize URL
    if not website_url.startswith(("http://", "https://")):
        website_url = f"https://{website_url}"

    logger.info(f"Starting analysis of {website_url}")

    # Extract domain as initial business name fallback
    domain_name = urlparse(website_url).netloc.replace("www.", "").split(".")[0]
    business_name = domain_name.title()

    # Fetch website content
    website_content = await _fetch_website_content(website_url)
    if not website_content:
        logger.warning(f"Could not fetch content from {website_url}")
        website_content = ""

    # Analyze content with LLM (with fallback to rule-based)
    analysis = await _analyze_with_llm(website_content, business_name, website_url)

    # Extract contact info and social media from raw content
    social_media = _extract_social_links(website_content)
    contact_info = _extract_contact_info(website_content)

    # Search for competitors
    industry = analysis.get("industry", "other")
    competitors = await _search_competitors(business_name, industry)

    # Determine recommended employees based on industry
    recommended_employees = INDUSTRY_ROLE_MAPPING.get(industry, INDUSTRY_ROLE_MAPPING["other"])

    # Build the business profile
    profile = BusinessProfile(
        business_name=analysis.get("business_name", business_name),
        website_url=website_url,
        industry=industry,
        description=analysis.get("description", ""),
        services=analysis.get("services", []),
        target_customer=analysis.get("target_customer", ""),
        tone=analysis.get("tone", "professional"),
        competitors=competitors,
        team_size_estimate=analysis.get("team_size_estimate", "small"),
        social_media=social_media,
        contact_info=contact_info,
        pain_points=analysis.get("pain_points", []),
        recommended_employees=recommended_employees,
    )

    return profile


def _save_profile_to_json(profile: BusinessProfile) -> Path:
    """Save the business profile to ~/.hermes/business_profile.json."""
    hermes_dir = Path.home() / ".hermes"
    hermes_dir.mkdir(parents=True, exist_ok=True)

    profile_path = hermes_dir / "business_profile.json"
    profile_dict = asdict(profile)

    with open(profile_path, "w") as f:
        json.dump(profile_dict, f, indent=2)

    logger.info(f"Profile saved to {profile_path}")
    return profile_path


async def main():
    """Entry point for the script."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/website_analyzer.py <website_url>")
        print("Example: python scripts/website_analyzer.py https://example.com")
        sys.exit(1)

    website_url = sys.argv[1]

    try:
        # Analyze the website
        profile = await analyze_website(website_url)

        # Save to JSON
        saved_path = _save_profile_to_json(profile)

        # Print summary
        print("\n" + "=" * 60)
        print(f"Business Profile: {profile.business_name}")
        print("=" * 60)
        print(f"Industry: {profile.industry}")
        print(f"Description: {profile.description}")
        print(f"Services: {', '.join(profile.services[:3])}")
        print(f"Tone: {profile.tone}")
        print(f"Team Size: {profile.team_size_estimate}")
        if profile.competitors:
            print(f"Competitors: {', '.join(profile.competitors[:3])}")
        print(f"Recommended Employees: {', '.join(profile.recommended_employees)}")
        print("=" * 60)
        print(f"Full profile saved to: {saved_path}")

    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
