import planunique_science_driver_v1 as P


def test_planunique_loader_delegates_to_reviewed_runtime_v1_without_loading_model():
    calls=[]
    old_runtime=P.runtime_v1.load_runtime
    had_inherited=hasattr(P.inherited_v2,"load_runtime")
    old_inherited=getattr(P.inherited_v2,"load_runtime",None)
    def reviewed(device):
        calls.append(("runtime_v1",device))
        return "TOK","MODEL",{"device_name":device}
    def forbidden(device):
        raise AssertionError("PLANUNIQUE_MUST_NOT_CALL_INHERITED_V2_LOAD_RUNTIME")
    P.runtime_v1.load_runtime=reviewed
    P.inherited_v2.load_runtime=forbidden
    try:
        out=P.load_runtime("TEST_DEVICE")
        assert out==("TOK","MODEL",{"device_name":"TEST_DEVICE"})
        assert calls==[("runtime_v1","TEST_DEVICE")]
    finally:
        P.runtime_v1.load_runtime=old_runtime
        if had_inherited:
            P.inherited_v2.load_runtime=old_inherited
        else:
            delattr(P.inherited_v2,"load_runtime")
