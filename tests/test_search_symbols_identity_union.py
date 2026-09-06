"""Gated finding 2026-09-05 (colibri review of tools/search_symbols.py, HIGH):
posting-list narrowing dropped identity-channel matches.

Candidates were the union of the posting lists for the query tokens, and the
full scan ran only when NO posting matched. `_identity_score` (prefix / segment
/ qualified-id) runs inside `_bm25_score`, so a symbol excluded by the narrowing
was never scored: query `foo` with `foo_helper` (tokens foo, helper) and `Foobar`
(token foobar) in the index scored `foo_helper` and silently never saw `Foobar`,
although the identity channel would have put it in the top tier. Fuzzy could not
rescue it (edit distance 3 > 2). Recall loss with no signal, worst exactly when
the query is a common token.
"""

from jcodemunch_mcp.tools.index_folder import index_folder
from jcodemunch_mcp.tools.search_symbols import search_symbols


def _seed(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text(
        "def foo_helper():\n    return 1\n\n"
        "class Foobar:\n    pass\n\n"
        "def foobaz_loader():\n    return 2\n\n"
        "def unrelated():\n    return 3\n"
    )
    idx = index_folder(path=str(tmp_path), use_ai_summaries=False, storage_path=str(tmp_path / "idx"))
    return idx["repo"], str(tmp_path / "idx")


def _names(result) -> list:
    return [r["name"] for r in result.get("results", [])]


def test_a_prefix_identity_match_survives_posting_list_narrowing(tmp_path):
    repo, storage = _seed(tmp_path)
    result = search_symbols(repo=repo, query="foo", max_results=10, storage_path=storage)
    names = _names(result)
    assert "foo_helper" in names, names  # the posting-list hit, still there
    assert "Foobar" in names, names  # identity prefix hit the narrowing used to drop
    assert "foobaz_loader" in names, names
    assert "unrelated" not in names, names


def test_the_identity_hit_outranks_a_mere_token_hit_of_equal_length(tmp_path):
    repo, storage = _seed(tmp_path)
    result = search_symbols(repo=repo, query="foobar", max_results=10, storage_path=storage)
    names = _names(result)
    assert names and names[0] == "Foobar", names


def test_packed_rows_are_charged_with_their_freshness_stamp(tmp_path):
    """Surfaced by the union: with more candidates the packer admitted rows by a
    cost measured BEFORE the FreshnessProbe stamped `_freshness` on them, and
    the delivered compact payload overshot token_budget (929B vs 800B in
    tests/test_v1_108_55.py). Rows must be stamped before packing, so the
    charge is the delivered row: tokens_used == payload // 4 exactly."""
    import json

    src = tmp_path / "src"
    src.mkdir()
    names = ["alpha", "alphabet", "alphanumeric", "alphonse", "alpine", "album",
             "alpha_one", "alpha_two", "alpha_three", "alpha_four"]
    body = "\n".join(f"    x{i} = {i}" for i in range(80))
    (src / "a.py").write_text("".join(f"def {n}(a, b, c):\n{body}\n\n" for n in names))
    idx = index_folder(path=str(tmp_path), use_ai_summaries=False, storage_path=str(tmp_path / "idx"))
    result = search_symbols(
        repo=idx["repo"], query="alpha", detail_level="compact",
        token_budget=200, max_results=5, storage_path=str(tmp_path / "idx"),
    )
    rows = result["results"]
    assert rows and all("_freshness" in r for r in rows)
    payload = sum(len(json.dumps(r, default=str)) for r in rows)
    assert payload <= 200 * 4, payload
    assert result["_meta"]["tokens_used"] == payload // 4, (result["_meta"]["tokens_used"], payload)
