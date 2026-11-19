-- STAND-IN: write this game version's unit type table, one "number name" line per unit type,
-- then quit. Unit type numbers (defID) change between game versions; the names do not.
-- Loaded only by dump_unit_defs.py.
local widget = widget

function widget:GetInfo()
  return {name="STAND-IN unit defs", desc="STAND-IN: dump the unit type table", layer=0, enabled=true}
end

function widget:Initialize()
  local f = assert(io.open("unit_defs.txt", "w"))
  f:write("# ", Game.gameVersion, "\n")
  for id, def in pairs(UnitDefs) do
    f:write(id, " ", def.name, "\n")
  end
  f:close()
  Spring.SendCommands("quitforce")
end
