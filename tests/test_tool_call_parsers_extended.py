"""
Extended tests for environments/tool_call_parsers/ — parsers not covered by
test_tool_call_parsers.py:

  DeepSeek V3.1, GLM 4.5, GLM 4.7, Kimi K2, Llama 3/4,
  Longcat, Qwen, Qwen3-Coder

Also adds a full-fleet contract test that validates every registered parser
against the ParseResult interface.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from environments.tool_call_parsers import (
        ParseResult,
        ToolCallParser,
        get_parser,
        list_parsers,
    )
except ImportError:
    pytest.skip("atroposlib not installed", allow_module_level=True)


# ─── helpers ────────────────────────────────────────────────────────────────

def _args(tc) -> dict:
    """Parse a tool call's arguments string to a dict."""
    return json.loads(tc.function.arguments)


# ─── Full-fleet contract (all registered parsers) ───────────────────────────

class TestAllParsersContract:
    """Every registered parser must satisfy the basic ParseResult contract."""

    @pytest.fixture(params=list_parsers())
    def parser(self, request):
        return get_parser(request.param)

    def test_plain_text_returns_text_and_none(self, parser):
        content, tool_calls = parser.parse("Hello, just plain text.")
        assert tool_calls is None
        assert content == "Hello, just plain text."

    def test_empty_string_does_not_raise(self, parser):
        result = parser.parse("")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_returns_two_element_tuple(self, parser):
        result = parser.parse("some text")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_garbage_input_does_not_raise(self, parser):
        # Partial / truncated / binary-ish strings must never crash the parser
        evil_inputs = [
            "\x00\x01\x02",
            "<tool_call>" * 100,
            "}{][",
            '{"name":',
            "null",
        ]
        for text in evil_inputs:
            content, tool_calls = parser.parse(text)
            # tool_calls must be None (no valid tool call was parsed)
            assert tool_calls is None, (
                f"parser {parser} returned tool_calls for garbage input {text!r}"
            )
            # content must be the original string or empty — never None for garbage
            assert content is None or isinstance(content, str), (
                f"parser {parser} returned non-string content for {text!r}"
            )

    def test_tool_calls_have_required_fields(self, parser):
        """When tool_calls is returned, every entry must have id, function.name, function.arguments."""
        # Use hermes format — not all parsers respond to it, so we only
        # assert on parsers that actually produce output here.
        text = '<tool_call>{"name": "ping", "arguments": {"x": 1}}</tool_call>'
        _, tool_calls = parser.parse(text)
        if tool_calls is None:
            return  # Parser doesn't handle hermes format — OK
        for tc in tool_calls:
            assert tc.id, "tool call id must be truthy"
            assert isinstance(tc.function.name, str)
            assert isinstance(tc.function.arguments, str)


# ─── DeepSeek V3.1 ──────────────────────────────────────────────────────────
# Format: <｜tool▁calls▁begin｜><｜tool▁call▁begin｜>name<｜tool▁sep｜>args<｜tool▁call▁end｜>

class TestDeepSeekV31Parser:
    @pytest.fixture
    def parser(self):
        return get_parser("deepseek_v3_1")

    def test_plain_text_no_tool_call(self, parser):
        content, tool_calls = parser.parse("Just chatting.")
        assert tool_calls is None
        assert content == "Just chatting."

    def test_single_tool_call(self, parser):
        text = (
            "<｜tool▁calls▁begin｜>"
            "<｜tool▁call▁begin｜>get_weather"
            "<｜tool▁sep｜>{\"city\": \"London\"}"
            "<｜tool▁call▁end｜>"
            "<｜tool▁calls▁end｜>"
        )
        content, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert len(tool_calls) == 1
        assert tool_calls[0].function.name == "get_weather"
        assert _args(tool_calls[0])["city"] == "London"

    def test_multiple_tool_calls(self, parser):
        text = (
            "<｜tool▁calls▁begin｜>"
            "<｜tool▁call▁begin｜>func_a<｜tool▁sep｜>{\"a\": 1}<｜tool▁call▁end｜>"
            "<｜tool▁call▁begin｜>func_b<｜tool▁sep｜>{\"b\": 2}<｜tool▁call▁end｜>"
            "<｜tool▁calls▁end｜>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert len(tool_calls) == 2
        names = {tc.function.name for tc in tool_calls}
        assert names == {"func_a", "func_b"}

    def test_preceding_text_stripped(self, parser):
        text = (
            "Let me check that.\n"
            "<｜tool▁calls▁begin｜>"
            "<｜tool▁call▁begin｜>terminal<｜tool▁sep｜>{\"command\": \"ls\"}"
            "<｜tool▁call▁end｜>"
        )
        content, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert content is not None and "Let me check" in content

    def test_arguments_preserved_verbatim(self, parser):
        """Arguments string should be passed through as-is, without reformatting."""
        args_str = '{"key": "value with spaces", "nested": {"x": true}}'
        text = (
            "<｜tool▁calls▁begin｜>"
            f"<｜tool▁call▁begin｜>my_func<｜tool▁sep｜>{args_str}"
            "<｜tool▁call▁end｜>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        # Compare raw string — not json.loads() of both (that hides whitespace/format bugs)
        assert tool_calls[0].function.arguments == args_str

    def test_also_registered_as_deepseek_v31(self, parser):
        """Same class registered under both names."""
        p2 = get_parser("deepseek_v31")
        assert type(p2) == type(parser)

    def test_ids_are_unique(self, parser):
        text = (
            "<｜tool▁calls▁begin｜>"
            "<｜tool▁call▁begin｜>f1<｜tool▁sep｜>{}<｜tool▁call▁end｜>"
            "<｜tool▁call▁begin｜>f1<｜tool▁sep｜>{}<｜tool▁call▁end｜>"
        )
        _, tool_calls = parser.parse(text)
        if tool_calls:
            ids = [tc.id for tc in tool_calls]
            assert len(ids) == len(set(ids))


# ─── GLM 4.5 ────────────────────────────────────────────────────────────────
# Format: <tool_call>func_name\n<arg_key>k</arg_key><arg_value>v</arg_value>\n</tool_call>

class TestGlm45Parser:
    @pytest.fixture
    def parser(self):
        return get_parser("glm45")

    def test_plain_text_no_tool_call(self, parser):
        content, tool_calls = parser.parse("No tools here.")
        assert tool_calls is None

    def test_single_tool_call_string_arg(self, parser):
        text = (
            "<tool_call>get_weather\n"
            "<arg_key>city</arg_key><arg_value>London</arg_value>\n"
            "</tool_call>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert len(tool_calls) == 1
        assert tool_calls[0].function.name == "get_weather"
        assert _args(tool_calls[0])["city"] == "London"

    def test_integer_arg_deserialized(self, parser):
        text = (
            "<tool_call>calculate\n"
            "<arg_key>n</arg_key><arg_value>42</arg_value>\n"
            "</tool_call>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert _args(tool_calls[0])["n"] == 42

    def test_boolean_arg_deserialized(self, parser):
        text = (
            "<tool_call>toggle\n"
            "<arg_key>enabled</arg_key><arg_value>true</arg_value>\n"
            "</tool_call>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert _args(tool_calls[0])["enabled"] is True

    def test_multiple_args(self, parser):
        text = (
            "<tool_call>send_message\n"
            "<arg_key>to</arg_key><arg_value>alice</arg_value>\n"
            "<arg_key>body</arg_key><arg_value>Hello</arg_value>\n"
            "</tool_call>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        args = _args(tool_calls[0])
        assert args["to"] == "alice"
        assert args["body"] == "Hello"

    def test_multiple_tool_calls(self, parser):
        text = (
            "<tool_call>func_a\n<arg_key>x</arg_key><arg_value>1</arg_value>\n</tool_call>\n"
            "<tool_call>func_b\n<arg_key>y</arg_key><arg_value>2</arg_value>\n</tool_call>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert len(tool_calls) == 2

    def test_content_before_tool_call(self, parser):
        text = (
            "I'll do that.\n"
            "<tool_call>terminal\n"
            "<arg_key>command</arg_key><arg_value>ls</arg_value>\n"
            "</tool_call>"
        )
        content, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert content and "I'll do that" in content


# ─── GLM 4.7 ────────────────────────────────────────────────────────────────
# Extends GLM 4.5 — same format but regex handles newlines between arg tags

class TestGlm47Parser:
    @pytest.fixture
    def parser(self):
        return get_parser("glm47")

    def test_is_glm45_subclass(self, parser):
        from environments.tool_call_parsers.glm45_parser import Glm45ToolCallParser
        assert isinstance(parser, Glm45ToolCallParser)

    def test_plain_text_no_tool_call(self, parser):
        _, tool_calls = parser.parse("Just text.")
        assert tool_calls is None

    def test_basic_tool_call(self, parser):
        text = (
            "<tool_call>get_weather\n"
            "<arg_key>city</arg_key><arg_value>Tokyo</arg_value>\n"
            "</tool_call>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert tool_calls[0].function.name == "get_weather"

    def test_newline_between_arg_tags(self, parser):
        """GLM 4.7 regex handles newlines between arg_key and arg_value."""
        text = (
            "<tool_call>search\n"
            "<arg_key>query</arg_key>\n<arg_value>python docs</arg_value>\n"
            "</tool_call>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        args = _args(tool_calls[0])
        assert args.get("query") == "python docs"


# ─── Kimi K2 ────────────────────────────────────────────────────────────────
# Format: <|tool_calls_section_begin|> ... <|tool_call_begin|>functions.name:idx
#          <|tool_call_argument_begin|>JSON<|tool_call_end|>

class TestKimiK2Parser:
    @pytest.fixture
    def parser(self):
        return get_parser("kimi_k2")

    def test_plain_text_no_tool_call(self, parser):
        _, tool_calls = parser.parse("Normal response.")
        assert tool_calls is None

    def test_single_tool_call_with_functions_prefix(self, parser):
        text = (
            "<|tool_calls_section_begin|>\n"
            "<|tool_call_begin|>functions.get_weather:0"
            "<|tool_call_argument_begin|>{\"city\": \"Paris\"}"
            "<|tool_call_end|>\n"
            "<|tool_calls_section_end|>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert len(tool_calls) == 1
        assert tool_calls[0].function.name == "get_weather"
        assert _args(tool_calls[0])["city"] == "Paris"

    def test_function_id_without_prefix(self, parser):
        """ID without 'functions.' prefix: 'terminal:0' → name 'terminal'."""
        text = (
            "<|tool_calls_section_begin|>\n"
            "<|tool_call_begin|>terminal:0"
            "<|tool_call_argument_begin|>{\"command\": \"ls\"}"
            "<|tool_call_end|>\n"
            "<|tool_calls_section_end|>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert tool_calls[0].function.name == "terminal"

    def test_original_id_preserved(self, parser):
        """The original function_id string (e.g., 'functions.foo:0') is kept as tc.id."""
        text = (
            "<|tool_calls_section_begin|>\n"
            "<|tool_call_begin|>functions.my_tool:3"
            "<|tool_call_argument_begin|>{\"x\": 1}"
            "<|tool_call_end|>\n"
            "<|tool_calls_section_end|>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert tool_calls[0].id == "functions.my_tool:3"

    def test_multiple_tool_calls(self, parser):
        text = (
            "<|tool_calls_section_begin|>\n"
            "<|tool_call_begin|>functions.func_a:0"
            "<|tool_call_argument_begin|>{\"a\": 1}"
            "<|tool_call_end|>\n"
            "<|tool_call_begin|>functions.func_b:1"
            "<|tool_call_argument_begin|>{\"b\": 2}"
            "<|tool_call_end|>\n"
            "<|tool_calls_section_end|>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert len(tool_calls) == 2
        names = {tc.function.name for tc in tool_calls}
        assert names == {"func_a", "func_b"}

    def test_singular_start_token_variant(self, parser):
        """Parser also accepts <|tool_call_section_begin|> (singular)."""
        text = (
            "<|tool_call_section_begin|>\n"
            "<|tool_call_begin|>my_func:0"
            "<|tool_call_argument_begin|>{\"k\": \"v\"}"
            "<|tool_call_end|>\n"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None

    def test_preceding_text_captured(self, parser):
        text = (
            "Here is my answer.\n"
            "<|tool_calls_section_begin|>\n"
            "<|tool_call_begin|>tool:0"
            "<|tool_call_argument_begin|>{}"
            "<|tool_call_end|>\n"
        )
        content, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert content and "Here is my answer" in content


# ─── Llama 3.x / 4 ─────────────────────────────────────────────────────────
# Format: bare JSON objects  {"name": "func", "arguments": {...}}
# Optional prefix: <|python_tag|>

class TestLlamaParser:
    @pytest.fixture
    def parser(self):
        return get_parser("llama3_json")

    def test_plain_text_no_json_no_tool_call(self, parser):
        _, tool_calls = parser.parse("Hello world, no JSON here.")
        assert tool_calls is None

    def test_single_tool_call_arguments_key(self, parser):
        text = '{"name": "terminal", "arguments": {"command": "ls -la"}}'
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert len(tool_calls) == 1
        assert tool_calls[0].function.name == "terminal"
        assert _args(tool_calls[0])["command"] == "ls -la"

    def test_parameters_key_accepted(self, parser):
        """Some Llama variants use 'parameters' instead of 'arguments'."""
        text = '{"name": "search", "parameters": {"query": "AI"}}'
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert tool_calls[0].function.name == "search"

    def test_json_without_name_ignored(self, parser):
        text = '{"unrelated": "data", "no": "name"}'
        _, tool_calls = parser.parse(text)
        assert tool_calls is None

    def test_multiple_tool_calls_in_sequence(self, parser):
        text = (
            '{"name": "func_a", "arguments": {"x": 1}}'
            ' some text '
            '{"name": "func_b", "arguments": {"y": 2}}'
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert len(tool_calls) == 2
        names = {tc.function.name for tc in tool_calls}
        assert names == {"func_a", "func_b"}

    def test_python_tag_prefix_accepted(self, parser):
        text = '<|python_tag|>{"name": "eval_code", "arguments": {"code": "1+1"}}'
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert tool_calls[0].function.name == "eval_code"

    def test_llama4_json_alias(self):
        p = get_parser("llama4_json")
        assert isinstance(p, type(get_parser("llama3_json")))

    def test_ids_are_unique(self, parser):
        text = (
            '{"name": "f", "arguments": {}}'
            '{"name": "f", "arguments": {}}'
        )
        _, tool_calls = parser.parse(text)
        if tool_calls and len(tool_calls) > 1:
            ids = [tc.id for tc in tool_calls]
            assert len(ids) == len(set(ids))

    def test_mixed_content_with_regular_json(self, parser):
        """Regular JSON objects without name+arguments fields are skipped."""
        text = '{"just": "config"} {"name": "real_tool", "arguments": {"a": 1}}'
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert len(tool_calls) == 1
        assert tool_calls[0].function.name == "real_tool"


# ─── Longcat ────────────────────────────────────────────────────────────────
# Format: <longcat_tool_call>{"name": ..., "arguments": ...}</longcat_tool_call>

class TestLongcatParser:
    @pytest.fixture
    def parser(self):
        return get_parser("longcat")

    def test_plain_text_no_tool_call(self, parser):
        _, tool_calls = parser.parse("No tools.")
        assert tool_calls is None

    def test_single_tool_call(self, parser):
        text = '<longcat_tool_call>{"name": "terminal", "arguments": {"command": "pwd"}}</longcat_tool_call>'
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert len(tool_calls) == 1
        assert tool_calls[0].function.name == "terminal"
        assert _args(tool_calls[0])["command"] == "pwd"

    def test_multiple_tool_calls(self, parser):
        text = (
            '<longcat_tool_call>{"name": "a", "arguments": {"x": 1}}</longcat_tool_call>\n'
            '<longcat_tool_call>{"name": "b", "arguments": {"y": 2}}</longcat_tool_call>'
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert len(tool_calls) == 2

    def test_preceding_text_preserved(self, parser):
        text = 'Sure, let me do that.\n<longcat_tool_call>{"name": "ping", "arguments": {}}</longcat_tool_call>'
        content, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert content and "Sure" in content

    def test_empty_arguments(self, parser):
        text = '<longcat_tool_call>{"name": "get_time", "arguments": {}}</longcat_tool_call>'
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert _args(tool_calls[0]) == {}

    def test_malformed_json_handled_gracefully(self, parser):
        text = '<longcat_tool_call>not valid json</longcat_tool_call>'
        result = parser.parse(text)
        assert isinstance(result, tuple)

    def test_truncated_tag_handled_gracefully(self, parser):
        """Unclosed tag at end of generation must not crash."""
        text = '<longcat_tool_call>{"name": "tool", "arguments": {"x": 1}'
        result = parser.parse(text)
        assert isinstance(result, tuple)

    def test_ids_are_unique(self, parser):
        text = (
            '<longcat_tool_call>{"name": "f", "arguments": {}}</longcat_tool_call>'
            '<longcat_tool_call>{"name": "f", "arguments": {}}</longcat_tool_call>'
        )
        _, tool_calls = parser.parse(text)
        if tool_calls and len(tool_calls) > 1:
            ids = [tc.id for tc in tool_calls]
            assert len(ids) == len(set(ids))


# ─── Qwen ────────────────────────────────────────────────────────────────────
# Inherits from Hermes — same <tool_call>JSON</tool_call> format

class TestQwenParser:
    @pytest.fixture
    def parser(self):
        return get_parser("qwen")

    def test_is_hermes_format_compatible(self, parser):
        text = '<tool_call>{"name": "terminal", "arguments": {"command": "ls"}}</tool_call>'
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert tool_calls[0].function.name == "terminal"

    def test_plain_text_returns_none_tool_calls(self, parser):
        _, tool_calls = parser.parse("No tools.")
        assert tool_calls is None

    def test_multiple_tool_calls(self, parser):
        text = (
            '<tool_call>{"name": "a", "arguments": {}}</tool_call>\n'
            '<tool_call>{"name": "b", "arguments": {}}</tool_call>'
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert len(tool_calls) == 2

    def test_inherits_from_hermes_parser(self):
        from environments.tool_call_parsers.hermes_parser import HermesToolCallParser
        qwen = get_parser("qwen")
        assert isinstance(qwen, HermesToolCallParser)


# ─── Qwen3-Coder ────────────────────────────────────────────────────────────
# Format: <tool_call><function=name><parameter=key>val</parameter></function></tool_call>

class TestQwen3CoderParser:
    @pytest.fixture
    def parser(self):
        return get_parser("qwen3_coder")

    def test_plain_text_no_tool_call(self, parser):
        _, tool_calls = parser.parse("Just text, nothing else.")
        assert tool_calls is None

    def test_single_tool_call_string_parameter(self, parser):
        text = (
            "<tool_call>\n"
            "<function=get_weather>\n"
            "<parameter=city>London</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert len(tool_calls) == 1
        assert tool_calls[0].function.name == "get_weather"
        assert _args(tool_calls[0])["city"] == "London"

    def test_integer_parameter(self, parser):
        text = (
            "<tool_call>\n"
            "<function=count>\n"
            "<parameter=n>42</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert _args(tool_calls[0])["n"] == 42

    def test_boolean_parameter(self, parser):
        text = (
            "<tool_call>\n"
            "<function=toggle>\n"
            "<parameter=enabled>true</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert _args(tool_calls[0])["enabled"] is True

    def test_null_parameter(self, parser):
        text = (
            "<tool_call>\n"
            "<function=set_val>\n"
            "<parameter=value>null</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert _args(tool_calls[0])["value"] is None

    def test_multiple_parameters(self, parser):
        text = (
            "<tool_call>\n"
            "<function=send_message>\n"
            "<parameter=to>alice</parameter>\n"
            "<parameter=body>Hello!</parameter>\n"
            "</function>\n"
            "</tool_call>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        args = _args(tool_calls[0])
        assert args["to"] == "alice"
        assert args["body"] == "Hello!"

    def test_multiple_tool_calls(self, parser):
        text = (
            "<tool_call><function=func_a><parameter=x>1</parameter></function></tool_call>\n"
            "<tool_call><function=func_b><parameter=y>2</parameter></function></tool_call>"
        )
        _, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert len(tool_calls) == 2
        names = {tc.function.name for tc in tool_calls}
        assert names == {"func_a", "func_b"}

    def test_preceding_text_captured(self, parser):
        text = (
            "Let me run that.\n"
            "<tool_call><function=terminal><parameter=command>ls</parameter></function></tool_call>"
        )
        content, tool_calls = parser.parse(text)
        assert tool_calls is not None
        assert content and "Let me run that" in content

    def test_truncated_tag_does_not_crash(self, parser):
        text = "<tool_call>\n<function=tool>\n<parameter=arg>val"
        result = parser.parse(text)
        assert isinstance(result, tuple)

    def test_ids_are_unique(self, parser):
        text = (
            "<tool_call><function=f><parameter=x>1</parameter></function></tool_call>"
            "<tool_call><function=f><parameter=x>2</parameter></function></tool_call>"
        )
        _, tool_calls = parser.parse(text)
        if tool_calls and len(tool_calls) > 1:
            ids = [tc.id for tc in tool_calls]
            assert len(ids) == len(set(ids))


# ─── _try_convert_value helper (Qwen3-Coder) ────────────────────────────────

class TestTryConvertValue:
    def setup_method(self):
        from environments.tool_call_parsers.qwen3_coder_parser import _try_convert_value
        self.convert = _try_convert_value

    def test_integer_string(self):
        assert self.convert("42") == 42

    def test_float_string(self):
        assert self.convert("3.14") == pytest.approx(3.14)

    def test_true_string(self):
        assert self.convert("true") is True

    def test_false_string(self):
        assert self.convert("false") is False

    def test_null_string(self):
        assert self.convert("null") is None

    def test_null_case_insensitive(self):
        assert self.convert("NULL") is None
        assert self.convert("Null") is None

    def test_json_object(self):
        assert self.convert('{"key": "value"}') == {"key": "value"}

    def test_json_array(self):
        assert self.convert('[1, 2, 3]') == [1, 2, 3]

    def test_plain_string(self):
        assert self.convert("hello world") == "hello world"


# ─── _deserialize_value helper (GLM 4.5) ────────────────────────────────────

class TestDeserializeValue:
    def setup_method(self):
        from environments.tool_call_parsers.glm45_parser import _deserialize_value
        self.deserialize = _deserialize_value

    def test_integer_string(self):
        assert self.deserialize("42") == 42

    def test_float_string(self):
        assert self.deserialize("3.14") == pytest.approx(3.14)

    def test_true_string(self):
        assert self.deserialize("true") is True

    def test_json_dict(self):
        assert self.deserialize('{"x": 1}') == {"x": 1}

    def test_plain_string(self):
        # Non-parseable value returned as-is
        assert self.deserialize("hello") == "hello"

    def test_python_tuple_via_ast(self):
        result = self.deserialize("(1, 2, 3)")
        assert result == (1, 2, 3)
