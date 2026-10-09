-- HD2-Addon: mods/codex/eagle_stratagem_profiles
-- Offline reference facts and conservative association; no engine/native access.
local P={catalog={}}
local generic={shape='direction',lo=-100,hi=100,half=6,estimated=false}
local function entry(id,name,tag,lo,hi,half,shape)
    P.catalog[id]={name=name,tag=tag,bounds={shape=shape or 'strip',lo=lo,hi=hi,
        half=half,radius=shape=='circle' and half or nil,estimated=shape~='direction'}}
end
-- These are baseline reference envelopes, not measured damage/safety boundaries.
-- Multi-bomb lengths include the catalog's assumed centre span plus two outer radii.
entry(18,'Eagle Airstrike','REF AIRSTRIKE',-60,60,10)
entry(30,'Eagle Strafing Run','REF STRAFE',-5,55,5)
entry(65,'Eagle Cluster Bomb','REF CLUSTER',-48,48,6)
-- User-calibrated reference: shorten the old 100 m envelope by 1/6 at each end.
entry(133,'Eagle Napalm Airstrike','REF NAPALM',-100/3,100/3,10)
entry(38,'Eagle Smoke Strike','REF SMOKE',-48,48,12)
entry(126,'Eagle Gas Airstrike','REF GAS',-48,48,12)
entry(3,'Eagle 500kg Bomb','REF 500KG',-25,25,25,'circle')
entry(140,'Eagle 110mm Rocket Pods','110MM TARGET ?',-100,100,6,'direction')

function P.bounds(id) return P.catalog[id] and P.catalog[id].bounds or generic end

local function near(a,b)
    if type(a)~='table' or type(b)~='table' then return false end
    for i=1,3 do
        if type(a[i])~='number' or type(b[i])~='number' or a[i]~=a[i] or b[i]~=b[i] then return false end
    end
    return (a[1]-b[1])^2+(a[2]-b[2])^2<=4 and math.abs(a[3]-b[3])<=6
end

function P.associate(impacts,rows,now,epoch)
    local claims,candidates,changed={},{},0
    for id,imp in pairs(impacts) do
        if imp.type_epoch~=epoch then
            if imp.stratagem_type then changed=changed+1 end
            imp.stratagem_type,imp.type_pending,imp.type_epoch,imp.type_logged=nil,nil,epoch,nil
        end
        local count,index=0,nil
        if type(rows)=='table' then
            for i,row in ipairs(rows) do
                -- Unsupported records still block a spatially ambiguous association.
                if near(imp.p,row.p) then
                    count,index=count+1,i
                    claims[i]=(claims[i] or 0)+1
                end
            end
        end
        if count==1 then candidates[id]=index end
    end
    for id,imp in pairs(impacts) do
        if not imp.stratagem_type then
            local i=candidates[id]
            if i and claims[i]==1 and P.catalog[rows[i].type] then
                local row=rows[i]
                local pending=imp.type_pending
                if pending and pending.id==row.type and near(pending.p,row.p)
                    and now>=pending.t and now-pending.t<=1 then
                    if now-pending.t>=0.12 then
                        imp.stratagem_type,imp.type_pending=row.type,nil
                        changed=changed+1
                    end
                else
                    imp.type_pending={id=row.type,p={row.p[1],row.p[2],row.p[3]},t=now}
                end
            else imp.type_pending=nil end
        end
    end
    return changed
end
return P
