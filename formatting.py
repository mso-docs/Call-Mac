"""Repair inline lists for display while preserving Markdown code."""
import re


def format_lists(text):
    """Put list items on separate lines without changing stored model responses."""
    # Never interpret numbers or operators inside code as list markers.
    parts = re.split(r"(`{3,}[^\n]*\n.*?\n`{3,}|~{3,}[^\n]*\n.*?\n~{3,}|`+[^`\n]*`+)", text, flags=re.S)
    for index in range(0, len(parts), 2):
        lines = []
        for line in parts[index].split("\n"):
            numbered = list(re.finditer(r"(?<!\S)(\d+)[.)][ \t]+(?=\S)", line))
            # Only repair a recognizable sequence, not arbitrary numbers in prose.
            if len(numbered) >= 2 and [int(m[1]) for m in numbered] == list(range(1, len(numbered) + 1)):
                line = re.sub(r"(?<=\S)[ \t]+(?=\d+[.)][ \t]+\S)", "\n", line)
                if numbered[0].start():
                    line = re.sub(r"(?<=\S)[ \t]+(?=1[.)][ \t]+\S)", "\n\n", line, count=1)
            # Hyphens and stars are bullets only in a line that starts a list,
            # or when introduced explicitly after a colon. Unicode bullets are explicit.
            if re.match(r"^\s*[-*•][ \t]+", line) or re.search(r":[ \t]+[-*•][ \t]+", line):
                line = re.sub(r"(?<=\S)[ \t]+(?=[-*•][ \t]+\S)", "\n", line)
            line = re.sub(r"(?<=\S)[ \t]+(?=•[ \t]+\S)", "\n", line)
            line = re.sub(r"(^|\n)([ \t]*)•[ \t]+", r"\1\2- ", line)
            lines.append(line)
        parts[index] = "\n".join(lines)
    return "".join(parts)
