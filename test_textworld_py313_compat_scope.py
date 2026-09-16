from __future__ import annotations

import copy
import unittest

import textworld.envs.pddl.textgen as tg

from textworld_py313_compat import install_evalsymbol_explicit_locals

ORIGINAL_DERIVE = tg.EvalSymbol.derive


class EvalSymbolScopeCompatTest(unittest.TestCase):
    def setUp(self):
        tg.EvalSymbol.derive = ORIGINAL_DERIVE
        if hasattr(tg.EvalSymbol, "_plancarry_explicit_locals"):
            delattr(tg.EvalSymbol, "_plancarry_explicit_locals")

    def test_upstream_python313_failure_shape(self):
        ctx = {"variables": {"r": 5}}
        with self.assertRaises(NameError):
            tg.EvalSymbol("r", ctx).derive()
        self.assertEqual(str(tg.EvalSymbol("self.expression", ctx).derive()[0]), "self.expression")
        self.assertEqual(str(tg.EvalSymbol("context['variables']['r']", ctx).derive()[0]), "5")

    def test_repair_preserves_scope_and_variables(self):
        ctx = {"variables": {"r": 5}}
        before = copy.deepcopy(ctx)
        install_evalsymbol_explicit_locals(tg)
        self.assertEqual(str(tg.EvalSymbol("r", ctx).derive()[0]), "5")
        self.assertEqual(str(tg.EvalSymbol("self.expression", ctx).derive()[0]), "self.expression")
        self.assertEqual(str(tg.EvalSymbol("context['variables']['r']", ctx).derive()[0]), "5")
        self.assertEqual(ctx, before)

    def test_context_precedence_builtins_globals_and_idempotence(self):
        install_evalsymbol_explicit_locals(tg)
        first = tg.EvalSymbol.derive
        install_evalsymbol_explicit_locals(tg)
        self.assertIs(first, tg.EvalSymbol.derive)
        base = {"variables": {"r": 2}}
        explicit = {"variables": {"r": 11}}
        obj = tg.EvalSymbol("r", base)
        self.assertEqual(str(obj.derive()[0]), "2")
        self.assertEqual(str(obj.derive(explicit)[0]), "11")
        self.assertGreater(int(str(tg.EvalSymbol("len(__name__)", {"variables": {}}).derive()[0])), 0)

    def test_variable_overlay_preserves_legacy_shadowing_intent(self):
        install_evalsymbol_explicit_locals(tg)
        ctx = {"variables": {"self": 17, "context": 23}}
        self.assertEqual(str(tg.EvalSymbol("self", ctx).derive()[0]), "17")
        self.assertEqual(str(tg.EvalSymbol("context", ctx).derive()[0]), "23")


if __name__ == "__main__":
    unittest.main(verbosity=2)
