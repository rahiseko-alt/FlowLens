"""#19: README.txt in the export and the consultant guide name only real tables/columns."""

import re
from pathlib import Path

from conftest import use

GUIDE = Path(__file__).resolve().parents[1] / "docs" / "consultant-guide.md"


def schema(exp):
    tables = [r["name"] for r in exp.rows("SELECT name FROM sqlite_master WHERE type='table'")]
    return {t: {c["name"] for c in exp.rows(f"PRAGMA table_info({t})")} for t in tables}


def test_readme_tables_and_columns_exist(recorder, export):
    use(recorder, "excel.exe", 0, 2)
    exp = export()
    tables = schema(exp)
    readme = exp.members["README.txt"].decode()
    described = re.findall(r"^- (\w+)\(([^)]*)\)", readme, flags=re.M)
    assert described
    for table, columns in described:
        assert table in tables, table
        for column in (c.strip() for c in columns.split(",")):
            assert column in tables[table], f"{table}.{column}"


def test_guide_tables_and_columns_exist(recorder, export):
    use(recorder, "excel.exe", 0, 2)
    tables = schema(export())
    guide = GUIDE.read_text(encoding="utf-8")
    for row in re.findall(r"^\| `(\w+)` \|(.*)$", guide, flags=re.M):
        name, rest = row
        if name.endswith((".sqlite", ".json", ".txt")):
            continue
        assert name in tables, name
        rest = re.sub(r"（[^）]*）|\([^)]*\)", "", rest)  # value lists in parentheses
        for column in re.findall(r"`(\w+)`", rest):
            assert column in tables[name], f"{name}: {column}"
