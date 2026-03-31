"""Tests for memory topic-file relevance scoring."""
import os
import tempfile
from agent.memory_selector import select_relevant_memories


def _make_memories_dir(topics: dict[str, str]) -> str:
    """Create a temp memories dir with MEMORY.md index and topic files."""
    d = tempfile.mkdtemp()
    index_lines = []
    for name, content in topics.items():
        with open(os.path.join(d, name), "w") as f:
            f.write(content)
        index_lines.append(f"- [{name}]({name}): {content[:50]}")
    with open(os.path.join(d, "MEMORY.md"), "w") as f:
        f.write("\n".join(index_lines))
    return d


def test_selects_relevant_topic():
    d = _make_memories_dir({
        "contacts.md": "# Contacts\nJohn Smith at Acme Corp, VP Sales",
        "personal.md": "# Personal\nUser prefers concise responses",
        "project_crm.md": "# CRM Project\nUsing Salesforce for pipeline tracking",
    })
    result = select_relevant_memories("what do we know about John Smith?", d)
    assert "John Smith" in result or "contacts" in result.lower()


def test_always_includes_personal():
    d = _make_memories_dir({
        "personal.md": "# Personal\nUser is a night owl",
        "contacts.md": "# Contacts\nSome contact data",
    })
    result = select_relevant_memories("what's the weather?", d)
    assert "night owl" in result


def test_falls_back_when_no_memory_dir():
    result = select_relevant_memories("hello", "/nonexistent/path")
    assert result == ""


def test_respects_max_topics():
    d = _make_memories_dir({
        f"topic_{i}.md": f"# Topic {i}\ncontent about topic {i}" for i in range(10)
    })
    result = select_relevant_memories("topic", d, max_topics=3)
    # Should not include all 10 topics
    topic_count = result.count("# Topic")
    assert topic_count <= 3


def test_falls_back_when_no_index():
    """Returns empty string when MEMORY.md doesn't exist."""
    d = tempfile.mkdtemp()
    # Write a topic file but no MEMORY.md index
    with open(os.path.join(d, "personal.md"), "w") as f:
        f.write("# Personal\nSome preference")
    result = select_relevant_memories("hello", d)
    assert result == ""


def test_empty_user_message_still_returns_personal():
    """Empty user message should still include personal.md."""
    d = _make_memories_dir({
        "personal.md": "# Personal\nUser likes Python",
        "contacts.md": "# Contacts\nJane Doe",
    })
    result = select_relevant_memories("", d)
    # personal.md is always included
    assert "Python" in result


def test_max_chars_per_topic_truncates():
    """Topic content is truncated at max_chars_per_topic."""
    long_content = "x" * 2000
    d = _make_memories_dir({
        "personal.md": long_content,
    })
    result = select_relevant_memories("test", d, max_chars_per_topic=100)
    # truncated marker should appear
    assert "truncated" in result or len(result) < 2000


def test_personal_always_first():
    """personal.md should appear before other topics in output."""
    d = _make_memories_dir({
        "personal.md": "# Personal\nPrefers brevity",
        "contacts.md": "# Contacts\ncontacts data here",
    })
    result = select_relevant_memories("contacts data", d)
    personal_pos = result.find("Prefers brevity")
    contacts_pos = result.find("contacts data here")
    if personal_pos >= 0 and contacts_pos >= 0:
        assert personal_pos < contacts_pos


def test_scores_by_keyword_overlap():
    """Topics with more keyword overlap should be ranked higher."""
    d = _make_memories_dir({
        "salesforce.md": "# Salesforce\nSalesforce CRM pipeline opportunities leads",
        "cooking.md": "# Cooking\nRecipes, ingredients, kitchen tools",
    })
    result = select_relevant_memories("salesforce pipeline leads", d, max_topics=1)
    # salesforce.md has more overlap, should be selected
    assert "Salesforce" in result or "salesforce" in result.lower()
    # cooking.md should not be selected with max_topics=1
    assert "Cooking" not in result
