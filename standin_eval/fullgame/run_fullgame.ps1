# STAND-IN: one command for "a checkpoint plays team 0 against BARb in a bar-harness game".
#
#   .\run_fullgame.ps1 -Checkpoint C:\Users\lolly\bar-standins\shared\ckpt\b03-h1\h1_best.pt
#   .\run_fullgame.ps1 -Checkpoint <path> -Games 3 -CapMinutes 20
#   .\run_fullgame.ps1 -Policy scripted -CapMinutes 2        # Roshan's scripted policy, no checkpoint
#
# It starts Team C's stand-in server on Windows with the checkpoint (torch is installed here,
# not in WSL), runs the game(s) in WSL with the copied run_game.py, and stops the server.
# Run folders: runs\game_<time>\. Local test fixture, not a result of any team.
param(
    [string]$Checkpoint = '',
    [ValidateSet('model', 'scripted', 'noop')] [string]$Policy = 'model',
    # The map name is a model input (a vocabulary entry). Give the name the checkpoint was
    # trained with; empty = the server's default, "Great Divide V1" (what b03-h1 was trained with).
    [string]$MapName = '',
    [switch]$Sample,            # sample the model's choices instead of taking the most likely ones
    [int]$SampleSeed = 0,       # seed of the sampling server's random stream (one stream per server start)
    # Team 1's AI (see OPPONENTS in scripts\run_game.py). 'barb' is what every earlier run used.
    [ValidateSet('barb', 'barb-easy', 'barb-medium', 'barb-hard-aggressive', 'simple',
                 'simple-defender', 'simple-constructor', 'null')] [string]$Opponent = 'barb',
    [int]$Games = 1,
    [double]$CapMinutes = 20,
    [switch]$KeepRequests,
    [switch]$SaveReplay,        # the engine also writes a replay file into <run folder>\demos
    # Another policy server with the same interface, e.g. standin_eval\unit_policy\server.py
    # (full path). Empty = Team C's stand-in server. -Temperature goes to it (1 = sampled, 0 = greedy).
    [string]$PolicyServer = '',
    [double]$Temperature = 1,
    [switch]$PlaceBuilds        # the widget moves a build order to the nearest place it can be built
)
$ErrorActionPreference = 'Stop'
$fullgame = $PSScriptRoot
$base = (Resolve-Path "$fullgame\..\..\..").Path             # C:\Users\lolly\bar-standins
if ($Policy -eq 'model' -and -not (Test-Path $Checkpoint)) { throw "Checkpoint not found: $Checkpoint" }

# 1. The policy server (Team C stand-in), with the checkpoint as its input.
$serverScript = 'standin_infer\server.py'
if ($Sample) {                                                             # same server, sample=True
    $serverScript = "$fullgame\scripts\sampling_server.py"
    $env:STANDIN_SAMPLE_SEED = "$SampleSeed"                               # read by sampling_server.py
}
if ($PolicyServer) {
    $serverScript = $PolicyServer
    $env:STANDIN_SAMPLE_SEED = "$SampleSeed"
    $env:STANDIN_TEMPERATURE = "$Temperature"
}
$serverArgs = @($serverScript, '--policy', $Policy)
if ($Policy -eq 'model') { $serverArgs += @('--checkpoint', (Resolve-Path $Checkpoint).Path) }
if ($MapName) { $serverArgs += @('--map-name', "`"$MapName`"") }     # quoted: the name has spaces
$server = Start-Process python -ArgumentList $serverArgs -WorkingDirectory "$base\team-c" `
    -RedirectStandardError "$fullgame\server.log" -WindowStyle Hidden -PassThru
try {
    $health = $null
    foreach ($try in 1..60) {                                # the model needs a few seconds to load
        try { $health = Invoke-RestMethod http://127.0.0.1:8765/health -TimeoutSec 2; break }
        catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $health) { throw 'The policy server did not answer /health; see server.log' }

    # 2. What is playing, copied into every run folder by run_game.py.
    $info = [ordered]@{ source = 'standin'; policy = $health.policy; checkpoint = $null; checkpoint_sha256 = $null
                        map_name_given_to_model = $MapName; sampled = [bool]$Sample; sampling_seed = $null }
    if ($Sample) { $info.sampling_seed = $SampleSeed }
    if ($PolicyServer) {
        $info.server_script = $PolicyServer; $info.sampled = ($Temperature -gt 0)
        $info.sampling_seed = $SampleSeed; $info.temperature = $Temperature
        # every STANDIN_* environment variable the server could read (queue depth, ...)
        $info.server_environment = [ordered]@{}
        Get-ChildItem env:STANDIN_* | ForEach-Object { $info.server_environment[$_.Name] = $_.Value }
    }
    $info.place_builds = [bool]$PlaceBuilds
    if ($Policy -eq 'model') {
        $info.checkpoint = (Resolve-Path $Checkpoint).Path
        $info.checkpoint_sha256 = (Get-FileHash $Checkpoint -Algorithm SHA256).Hash.ToLower()
    }
    # No BOM: Windows PowerShell's "-Encoding utf8" writes one, and Python's json would reject it.
    [IO.File]::WriteAllText("$fullgame\policy_info.json", ($info | ConvertTo-Json))

    # 3. The game(s), in WSL where Docker is. Same interpreter bar-harness uses (it has matplotlib).
    $linux = '/mnt/' + $fullgame.Substring(0, 1).ToLower() + $fullgame.Substring(2).Replace('\', '/')
    $gameArgs = @('scripts/run_game.py', '--cap-minutes', "$CapMinutes", '--games', "$Games",
                  '--opponent', $Opponent)
    if ($KeepRequests) { $gameArgs += '--keep-requests' }
    if ($SaveReplay) { $gameArgs += '--save-replay' }
    # docker writes its build progress to stderr. With 'Stop', Windows PowerShell would treat
    # those lines as errors when the output is redirected, so errors are not fatal from here on.
    $ErrorActionPreference = 'Continue'
    wsl -d Ubuntu-24.04 --cd "$linux" -- ~/bar-data/venv/bin/python @gameArgs
    "run_game.py exit code: $LASTEXITCODE"
}
finally {
    Stop-Process -Id $server.Id -Confirm:$false -ErrorAction SilentlyContinue     # 4. stop the server
}
