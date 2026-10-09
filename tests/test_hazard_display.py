"""The removed local hazard notice must not poll or add warning geometry."""
import unittest
from pathlib import Path

from test_mission_feedback import replay, THROW
from test_terrain_query import SCENE
from test_departure_options_performance import MENU


def player_call_prefix():
    return '''
local avatar={}
local old_query=sr.World.units_by_resource
local old_position=sr.Unit.world_position
local avatar_queries=0
local player={0,0,0}
local session={}
sr.Network.game_session=function() return session end
sr.Network.peer_id=function() return 7 end
sr.Network.object_info=function(kind)
    assert(kind=='un6y1d')
    return {fields={{id='b03b8bce'}}}
end
sr.GameSession.objects_owned_by=function(_,peer) assert(peer==7);return {501} end
sr.GameSession.game_object_exists=function(_,id) return id==501 end
sr.GameSession.game_object_is_type=function(_,id,kind) return id==501 and kind=='un6y1d' end
sr.GameSession.game_object_field=function(_,id,field)
    assert(id==501 and field=='index');return 0
end
sr.Unit.alive=function(unit) return unit==avatar end
sr.Unit.has_animation_state_machine=function() return true end
sr.Unit.animation_has_variable=function(_,name) return name=='player_number' end
sr.Unit.animation_find_variable=function(_,name) return name end
sr.Unit.animation_get_variable=function() return 0 end
sr.Unit.world_position=function(unit,...)
    if unit==avatar then return player end
    return old_position(unit,...)
end
sr.World.units_by_resource=function(world,key)
    if key=='content/fac_helldivers/cha_avatar/avatar_helldiver' then
        avatar_queries=avatar_queries+1;return {avatar}
    end
    return old_query(world,key)
end
'''


class HazardDisplayRemovalTest(unittest.TestCase):
    def test_saved_warning_key_is_ignored_and_no_player_poll_or_danger_geometry_remains(self):
        replay(SCENE + MENU + '''
saved['eagle_direction_probe.warn_player']=true
frames(45)
assert(rows['eagle_direction_probe.warn_player']==nil and M.warn_player==nil,
    'retired warning control must not be registered or restored from saved settings')
assert(saved['eagle_direction_probe.warn_player']==true,
    'compatibility check must not rewrite the obsolete saved key')
assert(#writes==14,'native-light authored-color option was not registered')
''')
        replay(SCENE + player_call_prefix() + THROW + '''
M.show_cordon=false -- no panel side-selection pose consumer
local imp=M.impacts[next(M.impacts)]
assert(imp and imp.stratagem_type==18,'fixture needs a confirmed Eagle impact')
player={imp.p[1],imp.p[2],imp.p[3]}
local before=avatar_queries
for _=1,45 do tick(1) end
assert(avatar_queries==before,'retired player warning still polls the local avatar')
assert(M.danger_state==nil and M.danger_signature==nil,
    'retired player warning state remains in the runtime')
for _,batch in ipairs({M.seg or {},M.flow_seg or {}}) do
    for _,segment in ipairs(batch) do
        assert(segment[1]~='danger','retired player warning still adds geometry')
    end
end
''')

    def test_source_no_longer_contains_hazard_poll_or_producer(self):
        source=(Path(__file__).resolve().parents[1]/'src/eagle_direction_probe.lua').read_text(encoding='utf-8')
        self.assertNotIn('update_player_danger',source)
        self.assertNotIn('append_danger_geometry',source)
        self.assertNotIn("'danger'",source)
        self.assertNotIn('warn_player',source)


if __name__ == '__main__':
    unittest.main()
