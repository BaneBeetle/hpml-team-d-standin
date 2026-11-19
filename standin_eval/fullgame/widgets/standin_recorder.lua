-- STAND-IN recorder widget: in a BARb vs BARb game, write some of the AIs' orders together with
-- the observation their team had just before. The rows become training data for a local
-- stand-in model. It only records; it gives no orders.
--
-- The observation is built exactly as the control widget builds it when a policy plays
-- (conservativeView for that team), so training and playing see the same fields.
-- Every `interval` frames it takes one observation per team. Of the orders that team's units
-- receive before the next observation, it keeps ONE, chosen at random, and writes one row.
-- (Keeping every order would repeat the full observation thousands of times per game.)
local widget = widget

function widget:GetInfo()
  return {name="HPML stand-in recorder", desc="STAND-IN: records AI orders with observations",
    author="stand-in", layer=100001, enabled=true}
end

local RUN = "LuaUI/Widgets/harness_run/"
local U = VFS.Include("LuaUI/hpml/bar_proof_common.lua",
  {Spring=Spring, string=string, table=table, math=math, type=type, tostring=tostring,
   pairs=pairs, ipairs=ipairs}, VFS.RAW_FIRST)

local config, out
local KEEP = 64     -- most orders written per team per window
local teams = {}    -- [teamID] = {ally=, state=, tick=, picked=, seen=, all=}

function widget:Initialize()
  local f = io.open(RUN .. "record_config.json", "r")
  if not f then widgetHandler:RemoveWidget(self); return end    -- not a recording run
  config = Json.decode(f:read("*a")); f:close()
  out = assert(io.open(RUN .. "recorded_orders.jsonl", "w"))
  local gaia = Spring.GetGaiaTeamID()
  for _, team in ipairs(Spring.GetTeamList()) do
    if team ~= gaia then
      teams[team] = {ally=select(6, Spring.GetTeamInfo(team, false)), seen=0}
    end
  end
end

function widget:GameFrame(frame)
  if not out or frame < config.first_frame or frame % config.interval ~= 0 then return end
  for team, t in pairs(teams) do
    if t.picked then    -- the row for the window that just ended
      -- action: the one order chosen at random (what make_pairs.py reads).
      -- actions: the window's first KEEP orders, in order (what unit_policy/build_dataset_barb.py reads).
      out:write(U.json({state_frame=t.tick, state_phase="GameFrame", action_frame=t.picked.frame,
        player_id=team, view_team=team, orders_in_window=t.seen, state=t.state, action=t.picked,
        actions=t.all}), "\n")
    end
    t.state = U.conservativeView(team, t.ally, Spring.GetAllUnits())
    t.tick, t.picked, t.seen, t.all = frame, nil, 0, {}
  end
  out:flush()
end

-- Called once per unit for every command a unit is given (the spectator sees all teams).
function widget:UnitCommand(unitID, unitDefID, unitTeam, cmdID, cmdParams, cmdOpts, cmdTag,
                            playerID, fromSynced, fromLua)
  local t = teams[unitTeam]
  if not out or not t or not t.state then return end
  t.seen = t.seen + 1
  local order = {frame=Spring.GetGameFrame(), command_id=cmdID, unit_ids={unitID},
    params=cmdParams, options=cmdOpts and cmdOpts.coded or 0, pairwise=false,
    player_id=playerID, from_synced=fromSynced, from_lua=fromLua}
  if #t.all < KEEP then t.all[#t.all + 1] = order end
  -- Keep the n-th order of the window with probability 1/n: each order is equally likely to stay.
  if math.random(t.seen) == 1 then t.picked = order end
end

function widget:Shutdown()
  if out then out:close() end
end
