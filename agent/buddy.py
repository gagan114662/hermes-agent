# agent/buddy.py
"""
Buddy companion system — port from CC's buddy/ directory.

Each user gets a deterministic companion (species, hat, rarity) seeded
from their user/session ID. The companion gains XP from interactions
and its state is persisted to ~/.hermes/buddy.json.

Ported from CC's buddy/companion.ts and buddy/types.ts.
"""
from __future__ import annotations
import json
import os
import logging
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

BUDDY_FILE = os.path.expanduser("~/.hermes/buddy.json")

# Species roster (from CC's buddy/types.ts)
SPECIES = ["duck", "cat", "dog", "fox", "bear", "rabbit", "penguin", "owl"]
HATS = ["none", "cap", "crown", "tophat", "beanie", "party", "wizard", "cowboy"]
RARITIES = ["common", "uncommon", "rare", "epic", "legendary"]
RARITY_WEIGHTS = [50, 30, 15, 4, 1]  # Out of 100


def _mulberry32(seed: int):
    """Tiny seeded PRNG — deterministic from seed."""
    a = seed & 0xFFFFFFFF
    def rng():
        nonlocal a
        a = (a + 0x6d2b79f5) & 0xFFFFFFFF
        t = ((a ^ (a >> 15)) * (1 | a)) & 0xFFFFFFFF
        t = (t + ((t ^ (t >> 7)) * (61 | t))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return rng


def _hash_string(s: str) -> int:
    h = 2166136261
    for c in s.encode():
        h ^= c
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _weighted_pick(rng, weights: list) -> int:
    """Pick index by weight."""
    total = sum(weights)
    r = rng() * total
    cumulative = 0
    for i, w in enumerate(weights):
        cumulative += w
        if r < cumulative:
            return i
    return len(weights) - 1


@dataclass
class Companion:
    species: str
    hat: str
    rarity: str
    name: str
    xp: int = 0
    level: int = 1
    interactions: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Companion":
        return cls(**d)

    def gain_xp(self, amount: int = 1) -> None:
        self.xp += amount
        self.interactions += 1
        # Level up every 100 XP
        self.level = 1 + self.xp // 100


def generate_companion(seed_string: str) -> Companion:
    """Generate a deterministic companion from a seed string (user/session ID)."""
    seed = _hash_string(seed_string)
    rng = _mulberry32(seed)

    species = SPECIES[int(rng() * len(SPECIES))]
    hat = HATS[int(rng() * len(HATS))]
    rarity_idx = _weighted_pick(rng, RARITY_WEIGHTS)
    rarity = RARITIES[rarity_idx]

    # Generate a short name from species + seed
    name_suffixes = ["Jr", "Sr", "III", "Max", "Mini", "Pro", "Plus"]
    suffix = name_suffixes[int(rng() * len(name_suffixes))]
    name = f"{species.capitalize()} {suffix}"

    return Companion(species=species, hat=hat, rarity=rarity, name=name)


def load_or_create_buddy(seed_string: str) -> Companion:
    """Load existing buddy or generate a new one."""
    try:
        if os.path.exists(BUDDY_FILE):
            with open(BUDDY_FILE) as f:
                data = json.load(f)
            return Companion.from_dict(data)
    except Exception:
        pass
    return generate_companion(seed_string)


def save_buddy(companion: Companion) -> None:
    """Persist buddy state to disk."""
    try:
        os.makedirs(os.path.dirname(BUDDY_FILE), exist_ok=True)
        tmp = BUDDY_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(companion.to_dict(), f, indent=2)
        os.replace(tmp, BUDDY_FILE)
    except Exception as e:
        logger.debug("save_buddy failed: %s", e)


def get_buddy_greeting(companion: Companion) -> str:
    """Get a brief companion greeting for CLI display."""
    rarity_emoji = {"common": "⭐", "uncommon": "⭐⭐", "rare": "⭐⭐⭐", "epic": "💫", "legendary": "✨"}
    hat_str = f" wearing a {companion.hat}" if companion.hat != "none" else ""
    return (
        f"{rarity_emoji.get(companion.rarity, '⭐')} {companion.name} "
        f"({companion.species}{hat_str}, Lv.{companion.level}) — "
        f"{companion.interactions} sessions together"
    )


def inherit_parent_cache(messages: list) -> list:
    """Prepend parent's cached message prefix so forked buddy subagent avoids
    re-paying for the cached prefix on its first API call.

    Only prepends if messages is short (fresh start) and a cached prefix exists.
    Safe to call always — fails silently if cache params are unavailable.
    """
    # Inherit parent's prompt cache to avoid re-paying for cached prefix
    try:
        from agent.prompt_caching import get_last_cache_safe_params
        cache_params = get_last_cache_safe_params()
        if cache_params and cache_params.cached_messages_prefix:
            # Only prepend if this looks like a fresh messages list (not already large)
            if len(messages) <= 2:
                logger.debug(
                    "[buddy] Inheriting %d cached messages from parent",
                    len(cache_params.cached_messages_prefix),
                )
                # Note: don't re-apply cache_control markers — they're already in the prefix
                return list(cache_params.cached_messages_prefix) + messages
    except ImportError:
        pass
    return messages
