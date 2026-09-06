"""Gated finding 2026-09-05 (colibri review of config.py, MEDIUM, probe-confirmed):
`_strip_jsonc`'s first pass popped a comma that sat immediately before `//` and
skipped a comma immediately after `*/`, so two valid JSONC shapes produced text
`json.loads` rejects - and `load_config` then substituted DEFAULTS for EVERY key
(one logger.error), `load_project_config` dropped the whole project overlay.
The second pass already removes genuine trailing commas before `}` / `]`.
"""

import json

import pytest

from jcodemunch_mcp.config import _strip_jsonc


@pytest.mark.parametrize(
    "text,expected",
    [
        ('{ "port": 8901,// c\n "host": "x" }', {"port": 8901, "host": "x"}),
        ('{ "a": 1 /* n */, "b": 2 }', {"a": 1, "b": 2}),
        # The shapes that already worked must keep working.
        ('{ "port": 8901, // c\n "host": "x" }', {"port": 8901, "host": "x"}),
        ('{ "a": 1, /* n */\n "b": 2 }', {"a": 1, "b": 2}),
        ('{ "a": 1, /* n */ "b": 2 }', {"a": 1, "b": 2}),
        ('{ "a": 1, // last\n}', {"a": 1}),
        ('{ "a": 1, /* last */\n}', {"a": 1}),
        ('{ "a": 1, /* last */ }', {"a": 1}),
        ('{ "a": 1, }', {"a": 1}),
        ('[1, 2, // c\n]', [1, 2]),
        ('{ "s": "a,// not a comment", "b": 2 }', {"s": "a,// not a comment", "b": 2}),
    ],
    ids=[
        "comma_then_linecomment_nospace",
        "blockcomment_then_comma",
        "comma_space_linecomment",
        "comma_blockcomment_newline",
        "comma_blockcomment_sameline",
        "trailing_comma_linecomment_close",
        "trailing_comma_blockcomment_newline_close",
        "trailing_comma_blockcomment_close",
        "trailing_comma_plain",
        "array_trailing_comma_comment",
        "comment_marker_inside_string",
    ],
)
def test_comment_comma_adjacency_round_trips(text, expected):
    assert json.loads(_strip_jsonc(text)) == expected
