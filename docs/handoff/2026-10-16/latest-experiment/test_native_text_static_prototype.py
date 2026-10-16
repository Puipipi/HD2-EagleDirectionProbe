from pathlib import Path

from lupa.luajit21 import LuaRuntime


HERE = Path(__file__).resolve().parent
MODULE = HERE / "native_text_static_prototype.lua"


FAKE_ENGINE = r"""
events = {}
call_order = {}
live_worlds = {}
epoch = 1
matrix_serial = 0
fail_at = nil
resource_mode = 'true'
material_result = 'ok'
destroy_failures = 0
worlds_throw = false
false_at = nil
identity_calls = 0
resource_checks = {}
local function record(name, ...)
  local source={...}
  local copied={}
  for i,value in ipairs(source) do
    if type(value)=='table' and value.tag=='matrix' then
      local m={tag='matrix-copy', epoch=value.epoch, serial=value.serial}
      for j=1,16 do m[j]=value[j] end
      copied[i]=m
    elseif type(value)=='table' and value.tag=='vector' then
      copied[i]={tag='vector-copy',epoch=value.epoch,x=value.x,y=value.y,z=value.z}
    else
      copied[i]=value
    end
  end
  call_order[#call_order + 1]='gui:'..name
  events[#events + 1] = {name=name, args=copied, epoch=epoch}
end
world = {tag='world'}
live_worlds[1] = world
gui = {tag='gui'}
resource_available = function(kind,path)
  call_order[#call_order + 1]='resource:'..kind
  resource_checks[#resource_checks+1]={kind=kind,path=path}
  if resource_mode == 'throw' then error('preflight failure') end
  if resource_mode == 'false' then return false end
  if resource_mode == 'font_only' and kind == 'material' then return false end
  if resource_mode == 'material_throw' and kind == 'material' then error('material preflight failure') end
  local expected_by_kind = {font='core/performance_hud/debug', material='core/performance_hud/debug'}
  return expected_by_kind[kind] ~= nil and path == expected_by_kind[kind]
end
stingray = {
  Application = {worlds=function()
    if worlds_throw then error('world enumeration unavailable') end
    return live_worlds
  end},
  Matrix4x4 = {identity=function()
    identity_calls = identity_calls + 1
    if false_at == 'pose' and identity_calls == 1 then return false end
    if false_at == 'text_pose' and identity_calls == 2 then return false end
    matrix_serial = matrix_serial + 1
    local m = {tag='matrix', epoch=epoch, serial=matrix_serial}
    for i=1,16 do
      if i == 1 or i == 6 or i == 11 or i == 16 then m[i]=1 else m[i]=0 end
    end
    return m
  end},
  Vector3 = setmetatable({}, {__call=function(_,x,y,z)
    if false_at == 'point' then return false end
    return {tag='vector', epoch=epoch, x=x,y=y,z=z}
  end}),
  World = {
    create_world_gui=function(w,pose,a,b)
      record('create_world_gui',w,pose,a,b)
      if fail_at == 'create_world_gui' then error('create failure') end
      if false_at == 'gui' then return false end
      return gui
    end,
    destroy_gui=function(w,g)
      record('destroy_gui',w,g)
      if destroy_failures > 0 then destroy_failures=destroy_failures-1; error('temporary destroy failure') end
      if fail_at == 'destroy_gui' then error('destroy failure') end
      if fail_at == 'destroy_false' then return false end
    end,
  },
  Gui = {
    material=function(g,path)
      record('material',g,path)
      if fail_at == 'material' then error('material failure') end
      if material_result == 'nil' then return nil end
      if material_result == 'false' then return false end
      return {tag='material', path=path}
    end,
    text_3d=function(g,text,font,size,material,tm,pos,layer,color)
      record('text_3d',g,text,font,size,material,tm,pos,layer,color)
      if fail_at == 'text_3d' then error('text failure') end
      if fail_at == 'nil_text_id' then return nil end
      if fail_at == 'invalid_text_id' then return -1 end
      if fail_at == 'fraction_text_id' then return 0.5 end
      return 23
    end,
    update_text_3d=function() error('must not update static text') end,
    destroy_text_3d=function() error('must not destroy text separately') end,
  },
}
"""


def runtime():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(FAKE_ENGINE)
    return lua


def create(lua, module, *args):
    result = module.create(*args, lua.globals().resource_available)
    if isinstance(result, tuple):
        return result
    return result, None


def test_module_is_inert_until_explicit_create_and_uses_known_call_shape():
    lua = runtime()
    module = lua.execute(MODULE.read_text(encoding="utf-8"))
    assert lua.eval("#events") == 0
    assert module["create"] is not None

    controller, reason = create(lua, module,
        lua.globals().stingray,
        lua.globals().world,
        lua.table_from([10, 20, 30]),
        5,
        "core/performance_hud/debug",
        100,
    )
    assert controller is not None, reason
    assert lua.eval("#events") == 3
    assert lua.eval("events[1].name") == "create_world_gui"
    assert lua.eval("events[2].name") == "material"
    assert lua.eval("events[3].name") == "text_3d"
    assert lua.eval("#resource_checks") == 2
    assert lua.eval("call_order[1] == 'resource:font' and call_order[2] == 'resource:material'")
    assert lua.eval("call_order[3] == 'gui:create_world_gui' and call_order[5] == 'gui:text_3d'")
    assert lua.eval("resource_checks[1].kind == 'font' and resource_checks[1].path == 'core/performance_hud/debug'")
    assert lua.eval("resource_checks[2].kind == 'material' and resource_checks[2].path == 'core/performance_hud/debug'")
    assert lua.eval("events[3].args[2]") == "EAGLE FONT"
    assert lua.eval("events[3].args[3]") == "core/performance_hud/debug"
    assert lua.eval("events[3].args[4]") == 1.0
    assert lua.eval("events[2].args[2]") == "core/performance_hud/debug"
    assert lua.eval("events[3].args[5]") == "core/performance_hud/debug"
    assert lua.eval("events[3].args[6].tag") == "matrix-copy"
    assert lua.eval("events[1].args[2].serial ~= events[3].args[6].serial")
    assert lua.eval("#events[3].args[6]") == 16
    assert lua.eval("events[3].args[6][1] == 1 and events[3].args[6][6] == 1 and events[3].args[6][16] == 1")
    assert lua.eval("events[3].args[7].tag") == "vector-copy"
    assert lua.eval("events[3].args[7].x == 10 and events[3].args[7].y == 20 and events[3].args[7].z == 30")
    assert lua.eval("events[3].args[8]") == 100
    assert lua.eval("events[3].args[9] == nil")
    assert controller["id"] is None
    assert controller["pose"] is None and controller["position"] is None

    # The fake arena advances immediately after the synchronous create call.
    # The returned controller must not retain either temporary engine value.
    lua.execute("epoch = epoch + 1")
    assert lua.eval("events[3].args[6].epoch + 1 == epoch")
    assert lua.eval("events[3].args[7].epoch + 1 == epoch")
    assert controller.cancel(controller)
    assert lua.eval("events[#events].name") == "destroy_gui"


def test_expiry_and_explicit_cancel_release_the_whole_gui_once():
    lua = runtime()
    module = lua.execute(MODULE.read_text(encoding="utf-8"))
    controller, reason = create(lua, module, lua.globals().stingray, lua.globals().world,
                                       lua.table_from([1, 2, 3]), 2,
                                       "core/performance_hud/debug", 10)
    assert controller is not None, reason
    assert not controller.tick(controller, 11, lua.globals().world)
    assert controller.tick(controller, 12, lua.globals().world)
    assert lua.eval("events[#events].name") == "destroy_gui"
    assert controller.tick(controller, 13, lua.globals().world)
    assert lua.eval("#events") == 4
    assert lua.eval("events[4].name") == "destroy_gui"
    assert lua.eval("events[4].args[1] == world")

    lua.execute("live_worlds = {}")
    controller2, reason = create(lua, module, lua.globals().stingray, lua.globals().world,
                                        lua.table_from([1, 2, 3]), 2,
                                        "core/performance_hud/debug", 10)
    assert controller2 is None
    assert reason == "world unavailable or unknown"


def test_expiry_destruction_failure_is_reported_and_can_be_retried():
    lua = runtime()
    module = lua.execute(MODULE.read_text(encoding="utf-8"))
    controller, reason = create(lua, module, lua.globals().stingray, lua.globals().world,
                                lua.table_from([1, 2, 3]), 2,
                                "core/performance_hud/debug", 10)
    assert controller is not None, reason
    lua.execute("fail_at = 'destroy_gui'")
    first = controller.tick(controller, 12, lua.globals().world)
    assert isinstance(first, tuple) and first[0] is False
    lua.execute("fail_at = nil")
    assert controller.tick(controller, 12, lua.globals().world)
    assert controller.tick(controller, 13, lua.globals().world)
    assert lua.eval("events[#events].name") == "destroy_gui"
    assert lua.eval("#events") == 5


def test_creation_failure_returns_retry_handle_when_rollback_fails():
    for failure, expected_reason in (("material", "font material bind failed"),
                                     ("invalid_text_id", "text creation failed")):
        lua = runtime()
        module = lua.execute(MODULE.read_text(encoding="utf-8"))
        lua.execute(f"fail_at = '{failure}'; destroy_failures = 2")
        result = module.create(lua.globals().stingray, lua.globals().world,
                               lua.table_from([1, 2, 3]), 2,
                               "core/performance_hud/debug", 10,
                               lua.globals().resource_available)
        assert isinstance(result, tuple) and len(result) == 3
        assert result[0] is None and result[1] == expected_reason
        cleanup = result[2]
        assert cleanup is not None
        first = cleanup.tick(cleanup, 10, lua.globals().world)
        assert isinstance(first, tuple) and first[0] is False
        assert cleanup.tick(cleanup, 10, lua.globals().world)
        assert cleanup.tick(cleanup, 10, lua.globals().world)
        assert lua.eval("events[#events].name") == "destroy_gui"
        assert lua.eval("#events") == (5 if failure == "material" else 6)


def test_unknown_world_state_preserves_handle_until_destroy_is_safe():
    lua = runtime()
    module = lua.execute(MODULE.read_text(encoding="utf-8"))
    controller, reason = create(lua, module, lua.globals().stingray, lua.globals().world,
                                lua.table_from([1, 2, 3]), 2,
                                "core/performance_hud/debug", 10)
    assert controller is not None, reason
    lua.execute("worlds_throw = true")
    result = controller.cancel(controller)
    assert isinstance(result, tuple) and result[0] is False
    assert lua.eval("#events") == 3
    lua.execute("worlds_throw = false")
    assert controller.cancel(controller)
    assert lua.eval("#events") == 4


def test_false_destroy_result_keeps_controller_retryable():
    lua = runtime()
    module = lua.execute(MODULE.read_text(encoding="utf-8"))
    controller, reason = create(lua, module, lua.globals().stingray, lua.globals().world,
                                lua.table_from([1, 2, 3]), 2,
                                "core/performance_hud/debug", 10)
    assert controller is not None, reason
    lua.execute("fail_at = 'destroy_false'")
    result = controller.cancel(controller)
    assert isinstance(result, tuple) and result[0] is False
    lua.execute("fail_at = nil")
    assert controller.cancel(controller)
    assert lua.eval("#events") == 5


def test_false_constructor_results_stop_before_the_next_native_stage():
    cases = {
        "pose": ("identity matrix unavailable", 0, None),
        "gui": ("world GUI unavailable", 1, None),
        "point": ("position vector unavailable", 3, "destroy_gui"),
        "text_pose": ("text matrix unavailable", 3, "destroy_gui"),
    }
    for false_at, (reason_expected, event_count, last_event) in cases.items():
        lua = runtime()
        module = lua.execute(MODULE.read_text(encoding="utf-8"))
        lua.execute(f"false_at = '{false_at}'")
        result = module.create(lua.globals().stingray, lua.globals().world,
                               lua.table_from([1, 2, 3]), 2,
                               "core/performance_hud/debug", 10,
                               lua.globals().resource_available)
        assert isinstance(result, tuple) and result[0] is None
        assert result[1] == reason_expected
        assert lua.eval("#events") == event_count, false_at
        if last_event is not None:
            assert lua.eval("events[#events].name") == last_event
        if event_count > 0:
            assert lua.eval("events[#events].name") != "text_3d"


def test_invalid_input_and_create_failures_never_leave_a_partial_gui():
    lua = runtime()
    module = lua.execute(MODULE.read_text(encoding="utf-8"))
    bad, reason = create(lua, module, lua.globals().stingray, lua.globals().world,
                                lua.table_from([float("nan"), 2, 3]), 2,
                                "core/performance_hud/debug", 10)
    assert bad is None and reason == "invalid position"
    assert lua.eval("#events") == 0

    expected_reasons = {"material": "font material bind failed",
                        "text_3d": "text creation failed",
                        "nil_text_id": "text creation failed",
                        "invalid_text_id": "text creation failed",
                        "fraction_text_id": "text creation failed"}
    for failure, expected_reason in expected_reasons.items():
        lua.execute(f"fail_at = '{failure}'")
        controller, reason = create(lua, module, lua.globals().stingray, lua.globals().world,
                                           lua.table_from([1, 2, 3]), 2,
                                           "core/performance_hud/debug", 10)
        assert controller is None, failure
        assert reason == expected_reason, (failure, reason)
        assert lua.eval("events[#events].name") == "destroy_gui", failure
        lua.execute("fail_at = nil")

    assert lua.eval("#events") == 19
    for i in (3, 7, 11, 15, 19):
        assert lua.eval(f"events[{i}].name") == "destroy_gui"


def test_world_loss_drops_owner_without_calling_destroy_on_dead_world():
    lua = runtime()
    module = lua.execute(MODULE.read_text(encoding="utf-8"))
    controller, reason = create(lua, module, lua.globals().stingray, lua.globals().world,
                                       lua.table_from([1, 2, 3]), 9,
                                       "core/performance_hud/debug", 10)
    assert controller is not None, reason
    lua.execute("live_worlds = {}")
    assert controller.tick(controller, 11, lua.globals().world)
    assert lua.eval("events[#events].name") == "text_3d"
    assert controller.cancel(controller)
    assert lua.eval("events[#events].name") == "text_3d"


def test_switching_current_world_releases_the_still_live_old_gui():
    lua = runtime()
    module = lua.execute(MODULE.read_text(encoding="utf-8"))
    controller, reason = create(lua, module, lua.globals().stingray, lua.globals().world,
                                lua.table_from([1, 2, 3]), 9,
                                "core/performance_hud/debug", 10)
    assert controller is not None, reason
    other_world = lua.table_from({"tag": "other-world"})
    assert controller.tick(controller, 11, other_world)
    assert lua.eval("events[#events].name") == "destroy_gui"
    assert lua.eval("events[#events].args[1] == world")


def test_gui_creation_failure_and_throwing_cleanup_are_safe_and_idempotent():
    lua = runtime()
    module = lua.execute(MODULE.read_text(encoding="utf-8"))
    lua.execute("fail_at = 'create_world_gui'")
    controller, reason = create(lua, module, lua.globals().stingray, lua.globals().world,
                                lua.table_from([1, 2, 3]), 2,
                                "core/performance_hud/debug", 10)
    assert controller is None and reason == "world GUI unavailable"
    assert lua.eval("#events") == 1
    assert lua.eval("events[1].name") == "create_world_gui"

    lua.execute("fail_at = nil")
    controller, reason = create(lua, module, lua.globals().stingray, lua.globals().world,
                                lua.table_from([1, 2, 3]), 2,
                                "core/performance_hud/debug", 10)
    assert controller is not None, reason
    lua.execute("fail_at = 'destroy_gui'")
    first = controller.cancel(controller)
    second = controller.cancel(controller)
    assert isinstance(first, tuple) and first[0] is False
    assert isinstance(second, tuple) and second[0] is False
    assert lua.eval("events[#events].name") == "destroy_gui"
    assert lua.eval("#events") == 6
    lua.execute("fail_at = nil")
    assert controller.cancel(controller)
    assert lua.eval("#events") == 7
    assert controller.cancel(controller)
    assert lua.eval("#events") == 7


def test_resource_preflight_is_required_and_fail_closed_before_gui_calls():
    cases = [
        (None, "resource preflight unavailable"),
        ("false", "font resource unavailable"),
        ("font_only", "material resource unavailable"),
        ("throw", "font resource unavailable"),
        ("material_throw", "material resource unavailable"),
    ]
    for mode, expected in cases:
        lua = runtime()
        module = lua.execute(MODULE.read_text(encoding="utf-8"))
        if mode is None:
            result = module.create(lua.globals().stingray, lua.globals().world,
                                   lua.table_from([1, 2, 3]), 2,
                                   "core/performance_hud/debug", 10)
            controller, reason = result
        else:
            lua.execute(f"resource_mode = '{mode}'")
            controller, reason = create(lua, module, lua.globals().stingray,
                                        lua.globals().world, lua.table_from([1, 2, 3]), 2,
                                        "core/performance_hud/debug", 10)
        assert controller is None
        assert reason == expected, (mode, reason)
        assert lua.eval("#events") == 0, mode


def test_material_binding_requires_non_null_value_and_rolls_back():
    for result in ("nil", "false"):
        lua = runtime()
        module = lua.execute(MODULE.read_text(encoding="utf-8"))
        lua.execute(f"material_result = '{result}'")
        controller, reason = create(lua, module, lua.globals().stingray, lua.globals().world,
                                    lua.table_from([1, 2, 3]), 2,
                                    "core/performance_hud/debug", 10)
        assert controller is None and reason == "font material bind failed"
        assert lua.eval("#events") == 3
        assert lua.eval("events[3].name") == "destroy_gui"


def test_ttl_must_be_bounded_and_expiry_sum_finite_before_gui_creation():
    lua = runtime()
    module = lua.execute(MODULE.read_text(encoding="utf-8"))
    for ttl, now in ((11, 10), (2, float("inf"))):
        controller, reason = create(lua, module, lua.globals().stingray, lua.globals().world,
                                    lua.table_from([1, 2, 3]), ttl,
                                    "core/performance_hud/debug", now)
        assert controller is None and reason == "invalid lifetime"
        assert lua.eval("#events") == 0


def test_only_the_audited_font_material_pair_is_accepted():
    lua = runtime()
    module = lua.execute(MODULE.read_text(encoding="utf-8"))
    controller, reason = create(lua, module, lua.globals().stingray, lua.globals().world,
                                lua.table_from([1, 2, 3]), 2,
                                "another/atlas.font", 10)
    assert controller is None and reason == "unsupported font path"
    assert lua.eval("#resource_checks") == 0
    assert lua.eval("#events") == 0


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"PASS: {len(tests)} native text static prototype contract tests")
