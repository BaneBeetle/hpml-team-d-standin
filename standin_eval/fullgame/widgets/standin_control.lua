-- STAND-IN control widget for a bar-harness game: a policy plays one team from the spectator client.
-- Written after Roshan's lua/control_loop_widget.lua (same request and response shapes, same
-- event names). What differs, and why:
--   * It runs in the spectator host, not a player: BAR hands LuaUI every team's stats only for a
--     full-view spectator, and bar-harness's stats widget needs them. Orders from a spectator
--     need god mode, which the start script turns on (see scripts/run_game.py).
--   * Files live in LuaUI/Widgets/harness_run/ because BAR's widget sandbox (luaui/barwidgets.lua)
--     lets user widgets write only under LuaUI/Config and LuaUI/Widgets.
--   * There is no fixture: it starts when the team has a unit, and the catalog is a placeholder.
--   * Paced mode only (the game is never paused), and no per-frame samples file.
local widget = widget

function widget:GetInfo()
  return {name="HPML stand-in control", desc="STAND-IN: observation/order bridge for one team",
    author="stand-in (after HPML Team D)", layer=100000, enabled=true}
end

local RUN = "LuaUI/Widgets/harness_run/"
local RESPONSE = RUN .. "policy_response.json"
-- Team A's/Roshan's helper file, unchanged, mounted outside LuaUI/Widgets so it is not loaded
-- as a widget. The sandbox gives an included file an empty environment unless one is passed.
local U = VFS.Include("LuaUI/hpml/bar_proof_common.lua",
  {Spring=Spring, string=string, table=table, math=math, type=type, tostring=tostring,
   pairs=pairs, ipairs=ipairs}, VFS.RAW_FIRST)

local config, events, pending, catalog, lastOrder
local team, allyTeam
local decision = 0
local initialized = false

-- One JSON line per event, in the file the Python bridge reads (Roshan's emit).
local function emit(kind, data)
  data = data or {}
  data.kind = kind
  data.engine_frame = Spring.GetGameFrame()
  data.match_id = config.match_id
  data.generation = config.generation
  data.player_id = Spring.GetMyPlayerID()
  data.team_id = team
  events:write(U.json(data), "\n")
  events:flush()
end

-- What the controlled team may know: its allies' units plus enemies in its line of sight.
local function observe()
  return U.conservativeView(team, allyTeam, Spring.GetAllUnits())
end

local function request(op, frame)
  local message = {protocol_version=1, match_id=config.match_id, generation=config.generation,
    player_id=Spring.GetMyPlayerID(), team_id=team, decision_id=decision, source_frame=frame,
    scheduled_frame=frame, op=op, observation=observe(), catalog=catalog,
    observation_phase="GameFrame before main simulation update",
    timing_mode="paced", decision_interval_frames=config.decision_interval_frames}
  emit("policy_request", {request=message, decision_id=decision, source_frame=frame})
  pending = message
end

function widget:Initialize()
  local f = io.open(RUN .. "control_config.json", "r")
  if not f then widgetHandler:RemoveWidget(self); return end    -- not a policy game (e.g. a recording run)
  config = Json.decode(f:read("*a")); f:close()
  team = config.control_team
  allyTeam = select(6, Spring.GetTeamInfo(team, false))
  -- This game version's unit type table (number -> name), for scripts/bridge.py: a checkpoint
  -- trained on another game version uses other numbers for the same units.
  local names = {}
  for id, def in pairs(UnitDefs) do names[tostring(id)] = def.name end
  local table_file = assert(io.open(RUN .. "unit_defs.json", "w"))
  table_file:write(U.json(names)); table_file:close()
  events = assert(io.open(RUN .. "policy_requests.jsonl", "w"))
  emit("bridge_start", {engine=Engine.version, game=Game.gameVersion, map=Game.mapName,
    spectator=Spring.GetSpectatingState()})
end

function widget:GameFrame(frame)
  if pending then return end      -- one outstanding decision; a slow reply skips decision ticks
  if not initialized then
    local first = (Spring.GetTeamUnits(team) or {})[1]
    if frame >= config.first_frame and first then
      -- validate_request requires Roshan's fixture catalog. Here it is a placeholder built from
      -- the team's first unit (its commander), enough for his ScriptedPolicy: move that unit
      -- 64 elmos, then build a solar collector beside where it started. target_id 0: no target.
      local x, y, z = Spring.GetUnitPosition(first)
      local side = select(5, Spring.GetTeamInfo(team, false))
      local solar = (side == "cortex") and "corsolar" or "armsolar"
      catalog = {builder_id=first, attacker_id=first, target_id=0,
        move_goal={x, Spring.GetGroundHeight(x, z - 64), z - 64},
        build_goal={x + 96, Spring.GetGroundHeight(x + 96, z), z},
        build_def_id=UnitDefNames[solar].id, move_command=CMD.MOVE, attack_command=CMD.ATTACK}
      initialized = true
      emit("control_ready", {god_mode=Spring.IsGodModeEnabled and Spring.IsGodModeEnabled(),
        cheating=Spring.IsCheatingEnabled()})
      request("reset", frame)
    end
  elseif frame % config.decision_interval_frames == 0 then
    decision = decision + 1
    request("predict", frame)
  end
end

-- Placement step for a build order that has a position. A player's interface does the same
-- for a human: BAR snaps an extractor to a metal spot and shows where a building cannot go.
--   extractor      -> the nearest metal spot where it can be built (BAR's own spot list),
--                     if one is within 800 elmos of the ordered position
--   other building -> the nearest place it can be built, within 1200 elmos (512 often found
--                     none for a factory near cliffs or water)
-- Changes a.params in place. Returns false when there is no such place.
local function place(a)
  local defID, facing = -a.command_id, a.params[4]
  local x = math.max(0, math.min(Game.mapSizeX, a.params[1]))
  local z = math.max(0, math.min(Game.mapSizeZ, a.params[3]))
  local finder = WG.resource_spot_finder
  if UnitDefs[defID].extractsMetal > 0 and finder and not finder.isMetalMap then
    local best, bestDistance
    for _, spot in ipairs(finder.metalSpotsList or {}) do
      local distance = (spot.x - x) ^ 2 + (spot.z - z) ^ 2
      if (not bestDistance or distance < bestDistance)
        and Spring.TestBuildOrder(defID, spot.x, spot.y, spot.z, facing) > 0 then
        best, bestDistance = spot, distance
      end
    end
    -- No free spot within 800 elmos of where the order pointed: drop the order. Without this
    -- limit an extractor order went to the nearest free spot anywhere, and once the spots near
    -- the base were taken that walked the commander across the map (2026-11-19).
    if not best or bestDistance > 800 ^ 2 then return false end
    x, z = best.x, best.z
  else
    local bx, _, bz = Spring.ClosestBuildPos(team, defID, x, Spring.GetGroundHeight(x, z), z, 1200, 0, facing)
    if not bx or bx < 0 then return false end
    x, z = bx, bz
  end
  a.params[1], a.params[2], a.params[3] = x, Spring.GetGroundHeight(x, z), z
  return true
end

function widget:Update()
  if not pending then return end
  local f = io.open(RESPONSE, "r")
  if not f then return end
  local text = f:read("*a"); f:close()
  local ok, reply = pcall(Json.decode, text)
  if not ok or type(reply) ~= "table" then return end    -- not readable yet: try again next update
  os.remove(RESPONSE)
  if reply.protocol_version ~= 1 or reply.op ~= pending.op or reply.player_id ~= pending.player_id
    or reply.team_id ~= pending.team_id or reply.match_id ~= pending.match_id
    or reply.generation ~= pending.generation or reply.decision_id ~= pending.decision_id
    or reply.source_frame ~= pending.source_frame then
    emit("response_rejected", {reason="identity mismatch"})
    return
  end
  -- engine_frame minus pending_from_frame = how far the game ran while the reply was pending.
  emit("policy_response_received", {response=reply, pending_from_frame=pending.source_frame,
    decision_id=pending.decision_id})
  if reply.status == "ok" and pending.op == "predict" and reply.action.kind == "order" then
    local a = reply.action
    if config.place_builds and a.command_id < 0 and #a.params == 4 and not place(a) then
      emit("order_dropped", {decision_id=pending.decision_id, order=a, reason="no place to build it"})
    elseif Spring.GetUnitTeam(a.unit_id) == team then
      lastOrder = {decision_id=pending.decision_id, unit_id=a.unit_id, command_id=a.command_id}
      Spring.GiveOrderToUnit(a.unit_id, a.command_id, a.params, a.options)
      emit("order_submitted", {decision_id=pending.decision_id, source_frame=pending.source_frame,
        order=a})
    else
      -- The game did not wait for the reply, so the recipient can be gone by now.
      emit("order_dropped", {decision_id=pending.decision_id, order=a,
        reason="recipient is no longer a unit of the controlled team"})
    end
  end
  pending = nil
end

-- The spectator sees every team's commands. Only the callback for our last order is recorded.
function widget:UnitCommand(unitID, unitDefID, unitTeam, cmdID, params)
  if events and lastOrder and lastOrder.unit_id == unitID and lastOrder.command_id == cmdID then
    emit("engine_command_callback", {unit_id=unitID, command_id=cmdID, params=params,
      decision_id=lastOrder.decision_id, evidence="diagnostic callback; not proof of execution"})
    lastOrder = nil
  end
end

function widget:GameOver(winners)
  if events then emit("game_over", {winners=winners}) end
end

function widget:Shutdown()
  if events then emit("bridge_shutdown"); events:close() end
end
