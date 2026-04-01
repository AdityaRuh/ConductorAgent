import fnmatch
import re


def parse_diff_files(diff: str) -> list[dict]:
    if not diff.strip():
        return []

    files = []
    parts = re.split(r"(?=^diff --git )", diff, flags=re.MULTILINE)

    for part in parts:
        part = part.strip()
        if not part.startswith("diff --git"):
            continue

        match = re.match(r"diff --git a/.+ b/(.+)", part)
        if not match:
            continue

        path = match.group(1)
        line_count = part.count("\n") + 1

        files.append({
            "path": path,
            "diff": part,
            "line_count": line_count,
        })

    return files


def _matches_pattern(path: str, pattern: str) -> bool:
    """Check if a file path matches a glob pattern.

    Hyphens in filenames are treated as equivalent to dots when matching,
    so that patterns like ``*.lock.json`` match files like ``package-lock.json``.
    """
    if fnmatch.fnmatch(path, pattern):
        return True
    # Normalise hyphens to dots in the path so that e.g. ``*.lock.json``
    # matches ``package-lock.json``.
    normalized = path.replace("-", ".")
    return fnmatch.fnmatch(normalized, pattern)


def filter_skip_files(files: list[dict], skip_patterns: list[str]) -> list[dict]:
    if not skip_patterns:
        return files

    result = []
    for f in files:
        path = f["path"]
        skip = any(_matches_pattern(path, pattern) for pattern in skip_patterns)
        if not skip:
            result.append(f)
    return result


def split_large_diff(files: list[dict], max_lines: int = 2000) -> list[list[dict]]:
    if not files:
        return []

    total_lines = sum(f["line_count"] for f in files)
    if total_lines <= max_lines:
        return [files]

    chunks = []
    current_chunk = []
    current_lines = 0

    for f in files:
        if current_lines + f["line_count"] > max_lines and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_lines = 0

        current_chunk.append(f)
        current_lines += f["line_count"]

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def reassemble_diff(files: list[dict]) -> str:
    return "\n".join(f["diff"] for f in files)
