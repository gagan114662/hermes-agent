"""Tests for buddy companion system."""
import pytest
from agent.buddy import generate_companion, Companion, get_buddy_greeting, _hash_string


def test_generate_companion_deterministic():
    """Same seed always produces same companion."""
    c1 = generate_companion("user-123")
    c2 = generate_companion("user-123")
    assert c1.species == c2.species
    assert c1.hat == c2.hat
    assert c1.rarity == c2.rarity
    assert c1.name == c2.name


def test_generate_companion_different_seeds():
    """Different seeds produce (usually) different companions."""
    companions = [generate_companion(f"user-{i}") for i in range(20)]
    species_set = {c.species for c in companions}
    # With 20 different seeds, we expect some variety
    assert len(species_set) > 1


def test_companion_rarity_is_valid():
    from agent.buddy import RARITIES
    for i in range(50):
        c = generate_companion(f"seed-{i}")
        assert c.rarity in RARITIES


def test_companion_xp_gain():
    c = Companion(species="duck", hat="cap", rarity="common", name="Duck Jr")
    c.gain_xp(50)
    assert c.xp == 50
    assert c.level == 1
    c.gain_xp(50)
    assert c.xp == 100
    assert c.level == 2


def test_buddy_greeting_contains_name():
    c = Companion(species="cat", hat="crown", rarity="rare", name="Cat III")
    greeting = get_buddy_greeting(c)
    assert "Cat III" in greeting
    assert "cat" in greeting


def test_buddy_save_and_load(tmp_path):
    from agent.buddy import save_buddy, load_or_create_buddy
    from unittest.mock import patch

    buddy_file = str(tmp_path / "buddy.json")
    c = generate_companion("test-seed-abc")
    c.gain_xp(10)

    with patch("agent.buddy.BUDDY_FILE", buddy_file):
        save_buddy(c)
        loaded = load_or_create_buddy("different-seed")  # seed ignored when file exists

    assert loaded.species == c.species
    assert loaded.xp == 10
