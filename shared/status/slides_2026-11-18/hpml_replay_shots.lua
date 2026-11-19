-- STAND-IN: while a replay plays, take screenshots at fixed game times, then quit.
-- Copied into the BAR install's LuaUI/Widgets only for the time of one replay (see take_replay_shots.ps1)
-- and removed again. In a normal game it removes itself and does nothing.
--
-- Every EVERY frames it takes three screenshots: team 0's base (the policy's team) from close,
-- the same from further away, then the whole map.
-- The engine saves them as <write dir>/screenshots/screenNNNNN.png, in the order taken.
function widget:GetInfo()
  return {name="HPML replay shots", desc="STAND-IN: screenshots of a replay at fixed game times",
    author="stand-in", layer=0, enabled=true}
end

local EVERY = 30 * 120        -- 2 game minutes (30 frames a second)
local SPEED = 15              -- playback speed asked for
local WAIT = 20               -- drawn frames between moving the camera and the screenshot
local steps = {}              -- what is left to do, in order: "close", "shot", "base", "shot", "map", "shot", ("quit")
local wait = 0
local nextFrame = EVERY
local speedSet = false

function widget:Initialize()
  if not Spring.IsReplay() then widgetHandler:RemoveWidget(self) end
end

local function lookAt(x, z, distance)
  local state = Spring.GetCameraState()
  state.px, state.py, state.pz = x, Spring.GetGroundHeight(x, z), z
  if state.dist then state.dist = distance end        -- the "spring" camera
  if state.height then state.height = distance end    -- the overhead camera
  Spring.SetCameraState(state, 0)
end

local function baseCentre()   -- the middle of team 0's units, or the map's middle when it has none
  local units = Spring.GetTeamUnits(0) or {}
  local sumX, sumZ, count = 0, 0, 0
  for _, unit in ipairs(units) do
    local x, _, z = Spring.GetUnitPosition(unit)
    if x then sumX, sumZ, count = sumX + x, sumZ + z, count + 1 end
  end
  if count == 0 then return Game.mapSizeX / 2, Game.mapSizeZ / 2 end
  return sumX / count, sumZ / count
end

local function plan(quitAfter)
  steps[#steps + 1] = "close"
  steps[#steps + 1] = "shot"
  steps[#steps + 1] = "base"
  steps[#steps + 1] = "shot"
  steps[#steps + 1] = "map"
  steps[#steps + 1] = "shot"
  if quitAfter then steps[#steps + 1] = "quit" end
end

function widget:GameFrame(frame)
  if not speedSet and frame > 30 then
    Spring.SendCommands("setmaxspeed " .. SPEED, "setminspeed " .. SPEED)
    speedSet = true
  end
  if frame >= nextFrame then
    nextFrame = nextFrame + EVERY
    plan(false)
  end
end

function widget:GameOver()
  plan(true)                  -- one last pair, then close the viewer
end

function widget:DrawScreen()  -- called once per drawn frame: do the next step when its wait is over
  if #steps == 0 then return end
  if wait > 0 then wait = wait - 1 return end
  local step = table.remove(steps, 1)
  if step == "close" or step == "base" then
    local x, z = baseCentre()
    lookAt(x, z, step == "close" and 1500 or 3200)
  elseif step == "map" then
    lookAt(Game.mapSizeX / 2, Game.mapSizeZ / 2, math.max(Game.mapSizeX, Game.mapSizeZ) * 1.1)
  elseif step == "shot" then
    Spring.SendCommands("screenshot png")
  elseif step == "quit" then
    Spring.SendCommands("quitforce")
  end
  wait = WAIT
end
