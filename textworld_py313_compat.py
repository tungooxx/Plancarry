"""Compatibility repair for TextWorld 1.7.0's Python 3.13 eval semantics."""
from __future__ import annotations

from types import ModuleType
from typing import Any


def install_evalsymbol_explicit_locals(textgen: ModuleType) -> None:
    """Preserve TextWorld's intended expression scope on Python 3.13+.

    TextWorld 1.7.0 mutates ``locals()`` before an implicit ``eval``.  That
    mutation is not guaranteed to be visible to eval in Python 3.13.  Supplying
    the grammar bindings explicitly is semantically equivalent to the
    pre-3.13 implementation and keeps the bindings isolated from mutation.
    """
    eval_symbol = textgen.EvalSymbol
    if getattr(eval_symbol, "_plancarry_explicit_locals", False):
        return

    def derive(self: Any, context: dict[str, Any] | None = None) -> list[Any]:
        active_context = context or self.context
        explicit_locals = {"self": self, "context": active_context}
        explicit_locals.update(dict(active_context["variables"]))
        value = eval(self.expression, textgen.__dict__, explicit_locals)
        return [textgen.TerminalSymbol(value)]

    eval_symbol.derive = derive
    eval_symbol._plancarry_explicit_locals = True
