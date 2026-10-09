"""Saved MOM height slider updates only ground geometry without terrain recasts."""
import unittest
from test_mission_feedback import replay
from test_solid_renderer import GUI
from test_type_display import FLAT
from test_departure_options_performance import MENU


HEIGHTS = '''
local function ground_height(expected)
    local n=0
    for _,batch in ipairs({M.seg,M.flow_seg}) do
        for _,s in ipairs(batch) do if s[1]=='ground' or s[1]=='flow' then
            for k=2,s[4] and 4 or 3 do
                assert(math.abs(s[k][3]-expected)<0.0001,'slider did not update actual ground geometry')
                n=n+1
            end
        end end
    end
    assert(n>0,'height check missed the ground geometry')
end
local function first_height(kind)
    for _,batch in ipairs({M.seg,M.flow_seg}) do
        for _,s in ipairs(batch) do if s[1]==kind then return s[2][3] end end
    end
    error('missing independent cue: '..kind)
end
'''


class GroundHeightOptionTest(unittest.TestCase):
    def test_apply_rebuilds_ground_at_slider_height_without_moving_other_cues_or_recasting(self):
        for renderer in ('', GUI):
            with self.subTest(solid=bool(renderer)):
                replay(renderer+FLAT+MENU+HEIGHTS+'''
frames(50)
local row=rows['eagle_direction_probe.ground_lift_cm']
assert(row and row.type=='slider' and row.min==0 and row.max==100 and row.step==1
    and row.default==8,'MOM height slider contract missing')
ground_height(0.08)
local marker,sky,plate=first_height('marker'),first_height('sky1'),first_height('cordon_dim')
local queries,impact,track=casts,M.impacts[1],M.tracks.design
local gui_count=gui_creates
for _,choice in ipairs({{35,0.35},{0,0},{100,1},{8,0.08}}) do
    apply('ground_lift_cm',choice[1]);frames(1)
    ground_height(choice[2])
    assert(first_height('marker')==marker and first_height('sky1')==sky
        and first_height('cordon_dim')==plate,'ground height moved upright or sky cues')
    assert(casts==queries and M.impacts[1]==impact and M.tracks.design==track,
        'height change restarted terrain queries or discarded a live strike')
    assert(gui_creates==gui_count,'height change recreated the native GUI')
end
''')

    def test_saved_height_restores_before_push_and_survives_a_new_menu_host(self):
        replay(GUI+FLAT+MENU+HEIGHTS+'''
local id='eagle_direction_probe.ground_lift_cm'
saved[id]=27
frames(50)
assert(M.ground_lift_cm==27 and values[id]==27,'saved height was overwritten by default')
ground_height(0.27)
apply('ground_lift_cm',42);frames(1)
ground_height(0.42)
values,rows,callbacks,writes={},{},{},{}
_G.ModOptionsMenu={api=1,register_option=host.register_option,get=host.get,
    set=host.set,on_change=host.on_change}
frames(25)
assert(M.ground_lift_cm==42 and values[id]==42,'new MOM host lost applied height')
ground_height(0.42)
local n=#writes
frames(25)
assert(#writes==n,'height setting was repeatedly written on a timer')
''')

    def test_restored_values_are_bounded_and_nonfinite_callbacks_do_not_poison_geometry(self):
        for value, expected in (('-9',0),('250',100),('12.6',13),('0/0',8),
                                ('math.huge',8),('false',8),("'bad'",8)):
            with self.subTest(value=value):
                replay(GUI+FLAT+MENU+HEIGHTS+f'''
saved['eagle_direction_probe.ground_lift_cm']={value}
frames(50)
assert(M.ground_lift_cm=={expected},'invalid saved height was not normalized')
ground_height({expected}/100)
local fn=callbacks['eagle_direction_probe.ground_lift_cm']
for _,invalid in ipairs({{0/0,math.huge,-math.huge,false,'bad'}}) do fn(invalid) end
frames(1)
ground_height({expected}/100)
assert(M.ground_lift_cm=={expected},'invalid callback changed the height')
''')


if __name__=='__main__': unittest.main()
