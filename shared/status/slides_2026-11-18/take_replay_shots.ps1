# STAND-IN: play one saved replay in the Windows BAR install and collect screenshots of it.
#
#   .\take_replay_shots.ps1 -Replay <full path of a .sdfz> -Name simple-3
#
# It opens a 1600x900 game window for the time of the replay (sound off), using a COPY of
# springsettings.cfg, so the install's own settings are not changed. The widget
# hpml_replay_shots.lua is copied into the install only while the replay plays and removed after.
# Screenshots end up in .\replay_<Name>\.
param(
    [Parameter(Mandatory)] [string]$Replay,
    [Parameter(Mandatory)] [string]$Name,
    [int]$MaxMinutes = 10
)
$ErrorActionPreference = 'Stop'
$data = 'C:\Users\lolly\AppData\Local\Programs\Beyond-All-Reason\data'
$engine = "$data\engine\recoil_2026.09.02\spring.exe"
$widget = "$data\LuaUI\Widgets\hpml_replay_shots.lua"
$shots = "$data\screenshots"
$out = Join-Path $PSScriptRoot "replay_$Name"

# 1. A copy of the settings with a small window and no sound.
$changed = 'Fullscreen', 'WindowBorderless', 'XResolutionWindowed', 'YResolutionWindowed',
           'WindowPosX', 'WindowPosY', 'snd_volmaster'
$lines = Get-Content "$data\springsettings.cfg" | Where-Object { ($_ -split '=')[0].Trim() -notin $changed }
$lines += 'Fullscreen = 0', 'WindowBorderless = 0', 'XResolutionWindowed = 1600', 'YResolutionWindowed = 900',
          'WindowPosX = 80', 'WindowPosY = 80', 'snd_volmaster = 0'
$config = Join-Path $env:TEMP 'hpml_springsettings.cfg'
[IO.File]::WriteAllLines($config, $lines)

# 2. The replay and the widget go into the install; remember which screenshots were there before.
$demo = Join-Path "$data\demos" (Split-Path $Replay -Leaf)
if (-not (Test-Path $demo)) { Copy-Item $Replay $demo }
New-Item -ItemType Directory -Force $shots, $out | Out-Null
$before = @(Get-ChildItem $shots -File | ForEach-Object Name)
Copy-Item (Join-Path $PSScriptRoot 'hpml_replay_shots.lua') $widget

# 3. Play it. The widget quits the viewer at game over; the time limit is for everything else.
try {
    $game = Start-Process $engine -PassThru -ArgumentList @(
        '--isolation', '--write-dir', "`"$data`"", '--config', "`"$config`"", "`"$demo`"")
    if (-not $game.WaitForExit($MaxMinutes * 60 * 1000)) {
        Stop-Process -Id $game.Id -Confirm:$false
        "stopped the viewer after $MaxMinutes minutes"
    }
}
finally {
    Remove-Item $widget -Confirm:$false -ErrorAction SilentlyContinue      # 4. our widget leaves the install
}

# 5. Move the new screenshots next to this script, numbered in the order taken.
$new = @(Get-ChildItem $shots -File | Where-Object { $_.Name -notin $before } | Sort-Object Name)
$number = 0
foreach ($file in $new) {
    $number += 1
    Move-Item $file.FullName (Join-Path $out ("{0}_{1:00}{2}" -f $Name, $number, $file.Extension))
}
"$($new.Count) screenshots in $out"
