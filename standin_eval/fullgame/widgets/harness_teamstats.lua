local widget = widget ---@type Widget

function widget:GetInfo()
	return {
		name = "Harness team stats dump",
		desc = "bar-harness: writes per-team stats every 15 s of game time, the GameOver winner, or a timeout at the cap, to JSON",
		author = "bar-harness",
		license = "GNU GPL, v2 or later",
		layer = 0, -- after the Team stats API widget (layer -828889), so WG.teamStats exists
		enabled = true,
	}
end

-- Data source: luarules/gadgets/api_teamstats.lua. The gadget hands LuaUI every team's
-- live values every 30 frames while a receiver is registered. Only one widget can hold
-- that receiver global, and BAR's "Team stats API" widget (luaui/Widgets/api_teamstats.lua)
-- holds it for everyone, so we register through it: WG.teamStats.subscribe(name, { live = fn }).
--
-- Output: OUT_PATH, rewritten whole after every sample (written to a .tmp file and renamed,
-- so a reader never sees half a file). User widgets may only write under LuaUI/Config and
-- LuaUI/Widgets (luaui/barwidgets.lua); bar-harness mounts the run folder at OUT_DIR.

local OUT_DIR = "LuaUI/Widgets/harness_run/"
local OUT_PATH = OUT_DIR .. "teamstats.json"
local TMP_PATH = OUT_PATH .. ".tmp"
local SUBSCRIBER = "bar_harness"
local SAMPLE_FRAMES = 15 * Game.gameSpeed -- 15 s of game time = 450 frames

-- The keys taken from each team's live values (names as the gadget gives them):
--   metalIncome, energyIncome  income per second
--   killedValue, lostValue     running totals of enemy value destroyed / own value lost (metal + energy/60)
--   metalSpots                 metal spots the team's extractors stand on
--   frontLine                  how far the ally team's army stands toward the enemy: per cent of the way
--                              from its start to the nearest enemy start, weighted by unit value
local FIELDS = { "metalIncome", "energyIncome", "killedValue", "lostValue", "metalSpots", "frontLine" }

local gaiaTeamID = Spring.GetGaiaTeamID()
local teamIDs = {} -- the players' teams, in order
local doc -- everything written to the file
local nextSampleFrame = SAMPLE_FRAMES

-- The game-time cap, if the startscript sets one: a "<frame>:quitforce" entry in the
-- debugcommands modoption (luarules/gadgets/cmd_dev_helpers.lua runs it at that frame).
-- One frame before it, a game nobody has won is written out as a timeout.
local capFrame
for frame in tostring((Spring.GetModOptions() or {}).debugcommands or ""):gmatch("(%d+):quitforce") do
	frame = tonumber(frame)
	if not capFrame or frame < capFrame then
		capFrame = frame
	end
end

-- JSON has no NaN or infinity, and the encoder would write them as bare words.
local function num(v)
	if type(v) ~= "number" or v ~= v or v == math.huge or v == -math.huge then
		return nil
	end
	return v
end

local function write()
	doc.written_frame = Spring.GetGameFrame()
	local ok, text = pcall(Json.encode, doc)
	if not ok then
		Spring.Echo("[bar-harness] JSON encode failed: " .. tostring(text))
		return
	end
	local file, err = io.open(TMP_PATH, "w")
	if not file then
		Spring.Echo("[bar-harness] cannot write " .. TMP_PATH .. ": " .. tostring(err))
		return
	end
	file:write(text)
	file:close()
	if not os.rename(TMP_PATH, OUT_PATH) then
		os.remove(OUT_PATH)
		os.rename(TMP_PATH, OUT_PATH)
	end
end

local function snapshot(all, frame)
	local teams = {}
	for i = 1, #teamIDs do
		local values = all[teamIDs[i]]
		if values then
			local row = { team = teamIDs[i], dead = values.dead == true }
			for k = 1, #FIELDS do
				row[FIELDS[k]] = num(values[FIELDS[k]])
			end
			teams[#teams + 1] = row
		end
	end
	return { frame = frame, seconds = frame / Game.gameSpeed, teams = teams }
end

local function onLive(all, frame)
	if doc.game_over or frame < nextSampleFrame then
		return
	end
	doc.samples[#doc.samples + 1] = snapshot(all, frame)
	nextSampleFrame = frame - frame % SAMPLE_FRAMES + SAMPLE_FRAMES
	write()
end

-- The state at the end: the last hand-over (at most 30 frames old), unless it was just sampled.
local function addFinalSample()
	local all, liveFrame
	if WG.teamStats and WG.teamStats.getLive then
		all, liveFrame = WG.teamStats.getLive()
	end
	local last = doc.samples[#doc.samples]
	if all and liveFrame and (not last or last.frame < liveFrame) then
		doc.samples[#doc.samples + 1] = snapshot(all, liveFrame)
	end
end

function widget:GameFrame(frame)
	if capFrame and frame >= capFrame - 1 and not doc.game_over and not doc.timeout then
		addFinalSample()
		doc.timeout = { frame = frame, seconds = frame / Game.gameSpeed, cap_frame = capFrame }
		doc.status = "timeout"
		write()
		Spring.Echo("[bar-harness] no winner by the cap at frame " .. capFrame .. ": timeout written")
	end
end

function widget:GameOver(winningAllyTeams)
	if doc.game_over then
		return
	end
	local frame = Spring.GetGameFrame()
	addFinalSample()
	-- An empty list is a draw.
	local allyTeams, teams = {}, {}
	for _, allyTeamID in ipairs(winningAllyTeams or {}) do
		allyTeams[#allyTeams + 1] = allyTeamID
		for _, teamID in ipairs(Spring.GetTeamList(allyTeamID) or {}) do
			if teamID ~= gaiaTeamID then
				teams[#teams + 1] = teamID
			end
		end
	end
	doc.game_over = {
		frame = frame,
		seconds = frame / Game.gameSpeed,
		winning_ally_teams = allyTeams,
		winning_teams = teams,
	}
	doc.status = "game_over"
	write()
	Spring.Echo("[bar-harness] GameOver at frame " .. frame .. ", winning ally teams: " .. table.concat(allyTeams, ","))
end

function widget:Initialize()
	local teamInfo = {}
	for _, teamID in ipairs(Spring.GetTeamList() or {}) do
		if teamID ~= gaiaTeamID then
			teamIDs[#teamIDs + 1] = teamID
			local _, _, _, isAI, side, allyTeamID = Spring.GetTeamInfo(teamID, false)
			local row = { team = teamID, ally_team = allyTeamID, side = side }
			if isAI then
				local _, aiName, _, shortName, version = Spring.GetAIInfo(teamID)
				row.ai = shortName
				row.ai_name = aiName
				row.ai_version = version
			end
			teamInfo[#teamInfo + 1] = row
		end
	end
	doc = {
		schema = 1,
		status = "running",
		map = Game.mapName,
		game = Game.gameName .. " " .. Game.gameVersion,
		engine = Engine.versionFull or Engine.version,
		sample_frames = SAMPLE_FRAMES,
		game_speed = Game.gameSpeed,
		cap_frame = capFrame,
		fields = FIELDS,
		teams = teamInfo,
		samples = {},
	}
	if not (WG.teamStats and WG.teamStats.subscribe) then
		doc.status = "error"
		doc.error = "WG.teamStats missing: the Team stats API widget is not loaded"
		Spring.Echo("[bar-harness] " .. doc.error)
		write()
		return
	end
	WG.teamStats.subscribe(SUBSCRIBER, { live = onLive })
	write()
	Spring.Echo("[bar-harness] team stats dump started: " .. OUT_PATH)
end

function widget:Shutdown()
	if WG.teamStats and WG.teamStats.unsubscribe then
		WG.teamStats.unsubscribe(SUBSCRIBER)
	end
end
