"""Turns title and file symbols into readable labels ("ファイル A", "画面 B").

The summary only ever shows labels. The label -> symbol table goes to a separate
file that is not given to the AI, so answers from the debrief can be tied back.
"""

from __future__ import annotations

from string import ascii_uppercase


def _letters(n: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA, ..."""
    out = ""
    n += 1
    while n:
        n, rem = divmod(n - 1, 26)
        out = ascii_uppercase[rem] + out
    return out


class Labeler:
    def __init__(self) -> None:
        self._by_symbol: dict[str, str] = {}
        self._count = {"ファイル": 0, "画面": 0}

    def label(self, symbol: str, ext: str) -> str:
        """The same symbol always gets the same label within one analysis."""
        if symbol not in self._by_symbol:
            kind = "ファイル" if ext else "画面"
            self._by_symbol[symbol] = f"{kind} {_letters(self._count[kind])}"
            self._count[kind] += 1
        return self._by_symbol[symbol]

    def table(self) -> dict[str, str]:
        return {label: symbol for symbol, label in self._by_symbol.items()}
