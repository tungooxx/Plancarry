from types import ModuleType

from textworld_py313_compat import install_evalsymbol_explicit_locals


def test_evalsymbol_uses_explicit_grammar_variables_and_is_idempotent():
    module = ModuleType("fake_textgen")

    class TerminalSymbol:
        def __init__(self, value):
            self.value = value

    class EvalSymbol:
        def __init__(self, expression, context):
            self.expression = expression
            self.context = context

    module.TerminalSymbol = TerminalSymbol
    module.EvalSymbol = EvalSymbol
    install_evalsymbol_explicit_locals(module)
    install_evalsymbol_explicit_locals(module)

    context = {"variables": {"r": 7}}
    result = module.EvalSymbol("r + 5", context).derive()

    assert [x.value for x in result] == [12]
    assert context == {"variables": {"r": 7}}
