"""Tests for the leak check of export_public.py (run: python -I -B test_export_public.py [--forbidden FILE]).

The real forbidden patterns (local paths, identity) live in a local unpublished file, so every test here uses
synthetic ones: a made-up first name and a made-up drive letter. The last test runs the real package against
the real file when `--forbidden FILE` is given; without it the run says so on its last line.
Run with -B: without it Python writes `__pycache__`, which the check rejects.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_public import check, forbidden_hits, load_patterns  # noqa: E402

PATTERNS = [r"zorblax", r"Z:[/\\]", r"zork"]
CORPUS_TEXT = "synthetic benchmark line with enough characters to fill a window of eighty and then more. " * 3
SECRET = "sk" + "-" + "a" * 25


def found(text: str) -> bool:
    return bool(forbidden_hits(text, PATTERNS))


def make_fixture(tmp: Path):
    """An upstream-like repo with one attack file, and an empty dest folder."""
    attack = tmp / "repo" / "attacks" / "cat" / "att"
    attack.mkdir(parents=True)
    (attack / "t.txt").write_text(CORPUS_TEXT, encoding="utf-8")
    dest = tmp / "dest"
    dest.mkdir()
    return tmp / "repo", dest


def test_name_caught_in_any_case():
    for variant in ("zorblax", "ZORBLAX", "Zorblax", "zORblax"):
        assert found(f"decided by {variant} on 2026-11-13"), variant
        assert found(variant + "'s decision"), variant


def test_paths_caught_in_any_case():
    assert found("Z" + ":\\" + "x")
    assert found("z" + ":/" + "x")
    assert found("ZORK")


def test_generic_secrets_caught_without_local_patterns():
    assert forbidden_hits(SECRET, [])
    assert forbidden_hits("API_" + "KEY=1", [])
    assert forbidden_hits("Bearer " + "b" * 25, [])


def test_clean_text_passes():
    assert not found("the author chose the questions, settings and each run")
    assert not found("l'auteur a choisi les questions")
    assert not found("python -I -B code/analyse.py data/scores-haiku45.jsonl --out out.json")


def test_load_patterns_reads_comments_and_blanks():
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "pats.txt"
        p.write_text("# comment\n\nabc\n  def  \n", encoding="utf-8")
        assert load_patterns(p) == ["abc", "def"]


def test_load_patterns_refuses_missing_or_empty_file():
    with tempfile.TemporaryDirectory() as t:
        for make in (lambda p: None, lambda p: p.write_text("# only a comment\n\n", encoding="utf-8")):
            p = Path(t) / "pats.txt"
            p.unlink(missing_ok=True)
            make(p)
            try:
                load_patterns(p)
            except ValueError:
                continue
            raise AssertionError("a missing or empty pattern file must raise")


def test_check_passes_on_clean_text_folder():
    with tempfile.TemporaryDirectory() as t:
        repo, dest = make_fixture(Path(t))
        (dest / "README.md").write_text("plain text\n", encoding="utf-8")
        assert check(repo, dest, PATTERNS) == 0


def test_check_fails_on_binary_file():
    with tempfile.TemporaryDirectory() as t:
        repo, dest = make_fixture(Path(t))
        (dest / "blob.bin").write_bytes(b"\x00\x01\x02")
        assert check(repo, dest, PATTERNS) == 1


def test_check_fails_on_invalid_utf8_in_text_suffix():
    with tempfile.TemporaryDirectory() as t:
        repo, dest = make_fixture(Path(t))
        (dest / "notes.txt").write_bytes(b"ok \xff\xfe broken")
        assert check(repo, dest, PATTERNS) == 1


def test_check_fails_on_pycache_even_with_text_suffix():
    with tempfile.TemporaryDirectory() as t:
        repo, dest = make_fixture(Path(t))
        (dest / "code" / "__pycache__").mkdir(parents=True)
        (dest / "code" / "__pycache__" / "x.py").write_text("print(1)\n", encoding="utf-8")
        (dest / "code" / "__pycache__" / "y.cpython-313.pyc").write_bytes(b"\x00\x00")
        assert check(repo, dest, PATTERNS) == 1


def test_check_fails_on_forbidden_pattern_and_on_leak():
    with tempfile.TemporaryDirectory() as t:
        repo, dest = make_fixture(Path(t))
        (dest / "a.md").write_text("written by zorblax\n", encoding="utf-8")
        assert check(repo, dest, PATTERNS) == 1
        (dest / "a.md").write_text("fine\n", encoding="utf-8")
        assert check(repo, dest, PATTERNS) == 0
        (dest / "b.md").write_text(CORPUS_TEXT, encoding="utf-8")  # copies the corpus text
        assert check(repo, dest, PATTERNS) == 1


def test_check_fails_on_empty_corpus():
    with tempfile.TemporaryDirectory() as t:
        (Path(t) / "dest").mkdir()
        (Path(t) / "dest" / "README.md").write_text("plain\n", encoding="utf-8")
        assert check(Path(t) / "no-such-repo", Path(t) / "dest", PATTERNS) == 1


def real_package_is_clean(forbidden_file: Path) -> None:
    """Every text file at the root of the package, against the real local pattern file."""
    root = Path(__file__).resolve().parent.parent
    patterns = load_patterns(forbidden_file)
    for n in ("README.md", "PROTOCOLE.md", "PROTOCOLE-Q2bis.md", "PLAN-CROISE.md", "LICENSE",
              ".gitignore", "code/export_public.py", "code/test_export_public.py"):
        text = (root / n).read_text(encoding="utf-8")
        assert not forbidden_hits(text, patterns), n


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)}/{len(tests)} tests OK")
    if "--forbidden" in sys.argv:
        real_package_is_clean(Path(sys.argv[sys.argv.index("--forbidden") + 1]))
        print("real package against the local pattern file: OK")
    else:
        print("real package against the local pattern file: NOT RUN (no --forbidden FILE given)")
