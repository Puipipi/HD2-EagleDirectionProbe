"""Read-only local-player pose resolver contract tests."""
from pathlib import Path
import unittest

from lupa.luajit21 import LuaRuntime


REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "src" / "local_player_pose.lua"


class LocalPlayerPoseTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime()
        self.lua.globals().module_path = str(MODULE)
        self.lua.execute("pose_module = assert(loadfile(module_path))()")

    def run_lua(self, body):
        self.lua.execute("""
            local module = pose_module
            local session, peer = {}, 'local-peer'
            local world, t = {}, 0
            local lookup_count, position_count, owned_count, object_info_count = 0, 0, 0, 0
            local avatar_field_count, sync_position_count = 0, 0
            local write_count = 0
            local player = {id=101,index=2,avatar_id=32767}
            local remote = {number=1,alive=true,pos={x=1,y=2,z=3,native_marker=true}}
            local own = {number=2,alive=true,pos={x=10,y=20,z=30,native_marker=true}}
            local units = {remote, own}
            local avatar_objects = {[201]={type='gl7xl2w',state=0,position={x=71,y=72,z=73,native_marker=true}}}
            local sr = {
                Network={
                    game_session=function() return session end,
                    peer_id=function() return peer end,
                    object_info=function(kind)
                        object_info_count=object_info_count+1
                        assert(kind=='un6y1d')
                        return {fields={{id='0xb03b8bce',name='index'}}}
                    end,
                    set_peer=function() write_count=write_count+1 end,
                },
                GameSession={
                    objects_owned_by=function(s,p) owned_count=owned_count+1; assert(s==session and p==peer); return {player.id} end,
                    game_object_exists=function(s,id) return id==player.id or avatar_objects[id]~=nil end,
                    game_object_is_type=function(s,id,kind)
                        if id==player.id then return kind=='un6y1d' end
                        return avatar_objects[id]~=nil and avatar_objects[id].type==kind
                    end,
                    game_object_field=function(s,id,key)
                        assert(s==session)
                        if id==player.id then
                            if key=='index' then return player.index end
                            if key=='baegche' then avatar_field_count=avatar_field_count+1; return player.avatar_id end
                        end
                        local avatar=avatar_objects[id]
                        if avatar then
                            if key=='state' then return avatar.state end
                            if key=='position' then sync_position_count=sync_position_count+1; return avatar.position end
                        end
                        return nil
                    end,
                    in_session=function() return true end,
                    set_field=function() write_count=write_count+1 end,
                },
                Unit={
                    alive=function(u) return u.alive end,
                    has_animation_state_machine=function() return true end,
                    animation_has_variable=function(_,name) return name=='player_number' end,
                    animation_find_variable=function(_,name) assert(name=='player_number'); return 17 end,
                    animation_get_variable=function(u,var) assert(var==17); return u.number end,
                    world_position=function(u,node) assert(node==1); position_count=position_count+1; return u.pos end,
                    set_position=function() write_count=write_count+1 end,
                },
                Vector3={
                    x=function(v) return v.x end,
                    y=function(v) return v.y end,
                    z=function(v) return v.z end,
                },
            }
            local resolver = module.new(sr,{avatar_units=function(w)
                assert(w==world); lookup_count=lookup_count+1; return units
            end})
        """ + body)

    def test_selects_peer_index_two_when_remote_avatar_is_first(self):
        self.run_lua("""
            local p,status=resolver:sample(world,0)
            assert(status=='OK' and p and p.x==10 and p.y==20 and p.z==30)
            assert(p.native_marker==nil)
            assert(lookup_count==1 and position_count==1)
        """)

    def test_uses_peer_owned_avatar_position_before_enumerating_unit_rigs(self):
        self.run_lua("""
            player.avatar_id=201
            sr.Network.object_info=function() return {fields={}} end
            local p,status,source=resolver:sample(world,0)
            assert(status=='OK' and p.x==71 and p.y==72 and p.z==73)
            assert(source=='network_avatar')
            assert(lookup_count==0 and position_count==0)
            assert(p.native_marker==nil)
        """)

    def test_unavailable_avatar_field_uses_strict_index_matched_rig_fallback(self):
        self.run_lua("""
            sr.GameSession.game_object_field=function(s,id,key)
                if key=='baegche' then error('field unavailable') end
                if id==player.id and key=='index' then return player.index end
                return nil
            end
            local p,status,source=resolver:sample(world,0)
            assert(status=='OK' and p.x==10 and p.y==20 and p.z==30)
            assert(source=='animation_fallback')
            assert(lookup_count==1 and position_count==1)
        """)

    def test_unavailable_synchronized_position_uses_strict_index_matched_rig_fallback(self):
        self.run_lua("""
            player.avatar_id=201
            avatar_objects[201].position=nil
            local p,status=resolver:sample(world,0)
            assert(status=='OK' and p.x==10 and p.y==20 and p.z==30)
            assert(lookup_count==1 and position_count==1)
        """)

    def test_fallback_enumeration_error_is_not_reported_as_no_matching_avatar(self):
        self.run_lua("""
            player.avatar_id=32767
            resolver=module.new(sr,{avatar_units=function() error('enumeration failed') end})
            local p,status=resolver:sample(world,0)
            assert(p==nil and status=='AVATAR_ENUMERATION_UNAVAILABLE')
        """)

    def test_missing_avatar_state_fails_closed_without_selecting_rig(self):
        self.run_lua("""
            player.avatar_id=201
            avatar_objects[201].state=nil
            local p,status,source=resolver:sample(world,0)
            assert(p==nil and status=='AVATAR_STATE_UNAVAILABLE')
            assert(source==nil)
            assert(lookup_count==0)
        """)

    def test_baegche_object_must_have_avatar_type_before_position_read(self):
        self.run_lua("""
            player.avatar_id=201
            avatar_objects[201].type='wrong-object-type'
            local p,status,source=resolver:sample(world,0)
            assert(p==nil and status=='AVATAR_TYPE_MISMATCH' and source==nil)
            assert(sync_position_count==0 and lookup_count==0)
        """)

    def test_avatar_type_read_error_fails_closed_until_identity_refresh(self):
        self.run_lua("""
            player.avatar_id=201
            sr.GameSession.game_object_is_type=function(s,id,kind)
                if id==201 then error('avatar type read failed') end
                return id==player.id and kind=='un6y1d'
            end
            local p,status,source=resolver:sample(world,0)
            assert(p==nil and status=='READ_FAILED:game_object_is_type' and source==nil)
            local again,again_status=resolver:sample(world,0.1)
            assert(again==nil and again_status=='READ_FAILED:game_object_is_type')
            assert(sync_position_count==0 and lookup_count==0)
        """)

    def test_avatar_state_read_error_stays_fail_closed_until_identity_refresh(self):
        self.run_lua("""
            player.avatar_id=201
            sr.GameSession.game_object_field=function(s,id,key)
                if id==player.id and key=='baegche' then return 201 end
                if id==201 and key=='state' then error('state read failed') end
                if id==player.id and key=='index' then return player.index end
                return nil
            end
            local p,status,source=resolver:sample(world,0)
            assert(p==nil and status=='READ_FAILED:game_object_field' and source==nil)
            local again,again_status,again_source=resolver:sample(world,0.1)
            assert(again==nil and again_status=='READ_FAILED:game_object_field' and again_source==nil)
            assert(lookup_count==0)
        """)

    def test_avatar_id_change_on_same_player_replaces_cached_position(self):
        self.run_lua("""
            player.avatar_id=201
            assert(resolver:sample(world,0).x==71)
            avatar_objects[202]={type='gl7xl2w',state=0,position={x=81,y=82,z=83}}
            player.avatar_id=202
            local p,status=resolver:sample(world,1.0)
            assert(status=='OK' and p.x==81 and p.y==82 and p.z==83)
            assert(lookup_count==0 and avatar_field_count==2 and owned_count==2)
        """)

    def test_nonzero_avatar_state_fails_closed_without_rig_fallback(self):
        self.run_lua("""
            player.avatar_id=201
            avatar_objects[201].state=1
            local p,status=resolver:sample(world,0)
            assert(p==nil and status=='AVATAR_NOT_ALIVE')
            assert(lookup_count==0)
        """)

    def test_nonzero_avatar_state_remains_fail_closed_until_identity_refresh(self):
        self.run_lua("""
            player.avatar_id=201
            assert(resolver:sample(world,0))
            avatar_objects[201].state=1
            local p,status,source=resolver:sample(world,1.0)
            assert(p==nil and status=='AVATAR_NOT_ALIVE' and source==nil and lookup_count==0)
            local again,again_status,again_source=resolver:sample(world,1.1)
            assert(again==nil and again_status=='AVATAR_NOT_ALIVE' and again_source==nil and lookup_count==0)
        """)

    def test_sentinel_avatar_uses_exact_player_index_rig_compatibility_path(self):
        self.run_lua("""
            player.avatar_id=32767
            local p,status=resolver:sample(world,0)
            assert(status=='OK' and p.x==10 and p.y==20 and p.z==30)
            assert(lookup_count==1 and position_count==1)
        """)

    def test_network_avatar_position_is_copied_and_cached_at_ten_hz(self):
        self.run_lua("""
            player.avatar_id=201
            local p,status,source=resolver:sample(world,0)
            assert(status=='OK' and source=='network_avatar')
            avatar_objects[201].position={x=91,y=92,z=93}
            local cached,cached_status,cached_source=resolver:sample(world,0.05)
            assert(cached_status=='OK' and cached==p and cached.x==71 and cached_source=='network_avatar')
            local updated=assert(resolver:sample(world,0.1))
            assert(updated.x==91 and updated.y==92 and updated.z==93 and updated~=p)
            assert(owned_count==1 and avatar_field_count==1 and sync_position_count==2)
        """)

    def test_invalid_network_position_reports_specific_failure_when_rig_fallback_fails(self):
        self.run_lua("""
            player.avatar_id=201
            avatar_objects[201].position={x=0/0,y=72,z=73}
            units={remote}
            local p,status=resolver:sample(world,0)
            assert(p==nil and status=='POSITION_INVALID')
            assert(lookup_count==1)
        """)

    def test_duplicate_matching_avatars_are_ambiguous(self):
        self.run_lua("""
            units={remote,own,{number=2,alive=true,pos={x=99,y=99,z=99}}}
            local p,status=resolver:sample(world,0)
            assert(p==nil and status=='AMBIGUOUS_AVATAR')
        """)

    def test_duplicate_entries_for_same_handle_are_unique(self):
        self.run_lua("""
            units={remote,own,own}
            local p,status=resolver:sample(world,0)
            assert(status=='OK' and p.x==10 and lookup_count==1)
        """)

    def test_avatar_read_failure_has_explicit_status_and_clears_pose(self):
        self.run_lua("""
            assert(resolver:sample(world,0))
            sr.Unit.alive=function() error('dead api') end
            local p,status=resolver:sample(world,0.1)
            assert(p==nil and status=='READ_FAILED:alive')
        """)

    def test_avatar_scan_read_failure_has_explicit_status(self):
        self.run_lua("""
            sr.Unit.animation_has_variable=function() error('animation api') end
            local p,status=resolver:sample(world,0)
            assert(p==nil and status=='READ_FAILED:animation_has_variable')
        """)

    def test_position_read_failure_has_explicit_status(self):
        self.run_lua("""
            sr.Unit.world_position=function() error('position api') end
            local p,status=resolver:sample(world,0)
            assert(p==nil and status=='READ_FAILED:world_position')
        """)

    def test_identity_is_refreshed_at_one_second_and_missing_identity_clears_pose(self):
        self.run_lua("""
            local first=assert(resolver:sample(world,0)); assert(first.x==10)
            assert(owned_count==1)
            player.index=1
            local next_pose,status=resolver:sample(world,1.0)
            assert(status=='OK' and next_pose.x==1 and owned_count==2 and lookup_count==2)
            sr.GameSession.objects_owned_by=function() owned_count=owned_count+1; return {} end
            local missing,missing_status=resolver:sample(world,2.0)
            assert(missing==nil and missing_status=='PLAYER_CALL_UNAVAILABLE')
            local cached,cached_status=resolver:sample(world,2.05)
            assert(cached==nil and cached_status=='PLAYER_CALL_UNAVAILABLE' and owned_count==3)
            resolver:sample(world,2.1)
            resolver:sample(world,2.9)
            assert(owned_count==3)
            local retry,retry_status=resolver:sample(world,3.0)
            assert(retry==nil and retry_status=='PLAYER_CALL_UNAVAILABLE' and owned_count==4)
        """)

    def test_duplicate_owned_player_calls_are_ambiguous(self):
        self.run_lua("""
            sr.GameSession.objects_owned_by=function() return {101,102} end
            sr.GameSession.game_object_exists=function(_,id) return id==101 or id==102 end
            sr.GameSession.game_object_is_type=function(_,_,kind) return kind=='un6y1d' end
            local p,status=resolver:sample(world,0)
            assert(p==nil and status=='AMBIGUOUS_PLAYER_CALL')
            assert(lookup_count==0)
        """)

    def test_missing_peer_or_required_api_is_explicitly_unavailable(self):
        self.run_lua("""
            sr.Network.peer_id=function() return nil end
            local p,status=resolver:sample(world,0)
            assert(p==nil and status=='PEER_UNAVAILABLE')
        """)
        self.setUp()
        self.run_lua("""
            sr.Network.peer_id=nil
            local p,status=resolver:sample(world,0)
            assert(p==nil and status=='API_UNAVAILABLE:Network.peer_id')
        """)

    def test_position_and_network_reads_are_limited_to_ten_hz(self):
        self.run_lua("""
            local p=assert(resolver:sample(world,0))
            local again,status=resolver:sample(world,0.05)
            assert(status=='OK' and again.x==p.x)
            assert(lookup_count==1 and position_count==1)
            resolver:sample(world,0.1)
            assert(lookup_count==1 and position_count==2)
        """)

    def test_avatar_enumeration_is_cached_for_one_second(self):
        self.run_lua("""
            resolver:sample(world,0)
            resolver:sample(world,0.1)
            resolver:sample(world,0.9)
            assert(lookup_count==1 and position_count==3)
            resolver:sample(world,1.0)
            assert(lookup_count==2 and position_count==4)
        """)

    def test_missing_avatar_does_not_reenumerate_before_one_second(self):
        self.run_lua("""
            units={remote}
            local _,first=resolver:sample(world,0)
            local _,second=resolver:sample(world,0.1)
            assert(first=='AVATAR_UNAVAILABLE' and second=='AVATAR_UNAVAILABLE')
            assert(lookup_count==1)
            local _,retry=resolver:sample(world,1.0)
            assert(retry=='AVATAR_UNAVAILABLE' and lookup_count==2)
        """)

    def test_dead_avatar_respawn_invalidates_cached_handle(self):
        self.run_lua("""
            local first=assert(resolver:sample(world,0)); assert(first.x==10)
            own.alive=false
            own={number=2,alive=true,pos={x=40,y=50,z=60}}
            units={remote,own}
            local next_pose,status=resolver:sample(world,0.1)
            assert(status=='OK' and next_pose.x==40 and lookup_count==2)
        """)

    def test_world_session_and_peer_changes_force_identity_rebind(self):
        self.run_lua("""
            resolver:sample(world,0); assert(lookup_count==1)
            local world2={}; world=world2
            resolver:sample(world,0.1); assert(lookup_count==2)
            session={}; resolver:sample(world,0.2); assert(lookup_count==3)
            peer='other-peer'; resolver:sample(world,0.3); assert(lookup_count==4)
        """)

    def test_world_change_invalidates_cache_without_exceeding_ten_hz(self):
        self.run_lua("""
            assert(resolver:sample(world,0))
            local world2={}; world=world2
            local p,status=resolver:sample(world,0.05)
            assert(p==nil and status=='WORLD_CHANGED' and lookup_count==1)
            p,status=resolver:sample(world,0.1)
            assert(status=='OK' and p.x==10 and lookup_count==2)
        """)

    def test_world_nil_clears_pose_without_returning_cached_coordinates(self):
        self.run_lua("""
            local p=assert(resolver:sample(world,0)); world=nil
            local missing,status=resolver:sample(world,0.01)
            assert(missing==nil and status=='WORLD_UNAVAILABLE')
        """)

    def test_missing_player_index_metadata_does_not_guess(self):
        self.run_lua("""
            sr.Network.object_info=function() object_info_count=object_info_count+1; return {fields={}} end
            local p,status=resolver:sample(world,0)
            assert(p==nil and status=='PLAYER_INDEX_FIELD_UNAVAILABLE')
            assert(lookup_count==0)
            resolver:sample(world,0.1)
            assert(owned_count==1 and object_info_count==1)
        """)

    def test_nonfinite_position_is_rejected(self):
        self.run_lua("""
            own.pos={x=0/0,y=20,z=30}
            local p,status=resolver:sample(world,0)
            assert(p==nil and status=='POSITION_INVALID')
        """)

    def test_returns_same_plain_cached_table_and_performs_reads_only(self):
        self.run_lua("""
            local p=assert(resolver:sample(world,0))
            assert(p~=own.pos and p.native_marker==nil)
            local cached=assert(resolver:sample(world,0.05))
            assert(cached.x==10 and cached==p and cached~=own.pos)
            assert(write_count==0)
        """)


if __name__ == "__main__":
    unittest.main()
