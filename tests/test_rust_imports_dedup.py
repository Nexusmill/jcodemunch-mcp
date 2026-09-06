"""Gated finding 2026-09-05 (colibri review of parser/imports.py, MEDIUM):
`_extract_rust_imports` de-duplicated on the first `::` segment, so
`use std::fs; use std::io;` recorded only `std::fs` and every later `use` from
the same crate was dropped - the Rust import graph under-counted for essentially
every real file (find_importers, blast radius, centrality).
"""

from jcodemunch_mcp.parser.imports import extract_imports

RUST = """\
use std::fs;
use std::io::{self, Read};
use std::collections::HashMap;
use crate::model::{Item, Store};
use crate::util;
use serde::Serialize;
use serde::Serialize;

fn main() {}
"""


def test_every_distinct_use_path_is_an_edge():
    edges = extract_imports(RUST, "src/main.rs", "rust")
    specs = [e["specifier"] for e in edges]
    assert specs == [
        "std::fs",
        "std::io",
        "std::collections::HashMap",
        "crate::model",
        "crate::util",
        "serde::Serialize",
    ], specs


def test_brace_names_stay_with_their_own_edge():
    edges = {e["specifier"]: e["names"] for e in extract_imports(RUST, "src/main.rs", "rust")}
    assert edges["crate::model"] == ["Item", "Store"]
    assert "Read" in edges["std::io"]
    assert edges["std::fs"] == []
