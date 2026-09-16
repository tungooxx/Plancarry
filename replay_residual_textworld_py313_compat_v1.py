#!/usr/bin/env python3
"""ReplayResidual-local compatibility shim for TextWorld 1.7.0 on Python >=3.13.

TextWorld 1.7.0 EvalSymbol.derive relies on mutating ``locals()`` and then
calling ``eval(expression)``.  CPython 3.13 no longer makes those injected
names visible to the subsequent implicit eval locals.  The intended pre-3.13
semantics are preserved by passing an explicit locals mapping containing the
function locals plus ``context['variables']``.

This module is process-local: it never edits installed TextWorld files.
"""
from __future__ import annotations

import sys
from typing import Any

_INSTALLED = False
_ORIGINAL_DERIVE = None


def install_textworld_py313_eval_compat() -> dict[str, Any]:
    """Install the narrow EvalSymbol.derive compatibility patch once.

    Returns provenance suitable for engineering/runtime logs.  On Python <3.13
    the patch is unnecessary and is left uninstalled.
    """
    global _INSTALLED, _ORIGINAL_DERIVE
    import textworld
    from textworld.envs.pddl import textgen

    if sys.version_info < (3, 13):
        return {
            "installed": False,
            "reason": "PYTHON_LT_3_13_REFERENCE_SEMANTICS",
            "python": sys.version,
            "textworld_version": getattr(textworld, "__version__", None),
        }
    if _INSTALLED:
        return {
            "installed": True,
            "reason": "ALREADY_INSTALLED",
            "python": sys.version,
            "textworld_version": getattr(textworld, "__version__", None),
        }

    _ORIGINAL_DERIVE = textgen.EvalSymbol.derive
    module_globals = vars(textgen)

    def _derive_explicit_locals(self: Any, context: Any = None):
        context = context or self.context
        # Match the intended <=3.12 function-local evaluation environment:
        # implicit locals contained `self` and `context`, then TextWorld tried
        # to inject context['variables'] via locals().update(...).
        eval_locals = {"self": self, "context": context}
        eval_locals.update(context["variables"])
        value = eval(self.expression, module_globals, eval_locals)
        return [textgen.TerminalSymbol(value)]

    _derive_explicit_locals.__name__ = "derive"
    _derive_explicit_locals.__qualname__ = "EvalSymbol.derive"
    textgen.EvalSymbol.derive = _derive_explicit_locals
    _INSTALLED = True
    return {
        "installed": True,
        "reason": "PYTHON_3_13_EXPLICIT_EVAL_LOCALS_COMPAT",
        "python": sys.version,
        "textworld_version": getattr(textworld, "__version__", None),
    }


def restore_textworld_eval_symbol_derive() -> bool:
    """Engineering-test helper; restore the process-local original method."""
    global _INSTALLED, _ORIGINAL_DERIVE
    if not _INSTALLED or _ORIGINAL_DERIVE is None:
        return False
    from textworld.envs.pddl import textgen
    textgen.EvalSymbol.derive = _ORIGINAL_DERIVE
    _ORIGINAL_DERIVE = None
    _INSTALLED = False
    return True
