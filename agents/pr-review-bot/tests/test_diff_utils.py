import pytest
from app.diff_utils import parse_diff_files, filter_skip_files, split_large_diff

SAMPLE_DIFF = """diff --git a/src/auth.py b/src/auth.py
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,3 +10,5 @@
 existing line
+new line 1
+new line 2
diff --git a/package-lock.json b/package-lock.json
--- a/package-lock.json
+++ b/package-lock.json
@@ -1,3 +1,5 @@
 existing
+added
diff --git a/dist/bundle.js b/dist/bundle.js
--- a/dist/bundle.js
+++ b/dist/bundle.js
@@ -1,3 +1,5 @@
 minified
+stuff"""


def test_parse_diff_files():
    files = parse_diff_files(SAMPLE_DIFF)
    assert len(files) == 3
    assert files[0]["path"] == "src/auth.py"
    assert files[1]["path"] == "package-lock.json"
    assert files[2]["path"] == "dist/bundle.js"


def test_filter_skip_files():
    files = parse_diff_files(SAMPLE_DIFF)
    skip_patterns = ["*.lock", "*.lock.json", "dist/**"]
    filtered = filter_skip_files(files, skip_patterns)
    assert len(filtered) == 1
    assert filtered[0]["path"] == "src/auth.py"


def test_filter_skip_files_no_patterns():
    files = parse_diff_files(SAMPLE_DIFF)
    filtered = filter_skip_files(files, [])
    assert len(filtered) == 3


def test_split_large_diff_under_threshold():
    files = parse_diff_files(SAMPLE_DIFF)
    chunks = split_large_diff(files, max_lines=2000)
    assert len(chunks) == 1


def test_split_large_diff_over_threshold():
    big_files = [
        {"path": f"file{i}.py", "diff": f"diff --git a/file{i}.py b/file{i}.py\n" + "\n".join(f"+line {j}" for j in range(1100)), "line_count": 1101}
        for i in range(3)
    ]
    chunks = split_large_diff(big_files, max_lines=2000)
    assert len(chunks) > 1


def test_parse_diff_files_empty():
    files = parse_diff_files("")
    assert files == []
