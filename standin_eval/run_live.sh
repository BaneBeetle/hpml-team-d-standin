#!/usr/bin/env bash
# STAND-IN launcher for this machine: the docker commands of scripts/run_control_loop.ps1,
# run inside WSL because Docker here exists only in WSL (no Docker Desktop).
#
# From Windows:
#   wsl -d Ubuntu-24.04 -- bash /mnt/c/Users/lolly/bar-standins/team-d/standin_eval/run_live.sh STEP ...
#
#   build                          build Roshan's image (his Dockerfile, unchanged)
#   prepare                        download the pinned engine, game and map into the Docker volume
#   roshan LABEL [loop args]       his run command plus --output (default ScriptedPolicy in the worker)
#   inside LABEL POLICY [loop args]  stand-in server (scripted|noop) inside the same container
#   host LABEL [loop args]         server already running on Windows 127.0.0.1:8765 (model policy)
#
# After a run, Roshan's result.json, trace.jsonl, trace.md and manifest.json are copied
# unchanged to shared/logs/live_LABEL_<match id>/. The full episode folder stays in the volume.
# Everything is a local test fixture.
set -eu

BASE=/mnt/c/Users/lolly/bar-standins
IMAGE=hpml-eval01:local
# The same two mounts as the .ps1: the repository at /work, the asset cache volume at /work/runtime.
MOUNTS="--mount type=bind,source=$BASE/team-d,target=/work --mount type=volume,source=hpml-eval01-runtime,target=/work/runtime"
# The stand-in adapter lives outside the repository. Mounted read-only; PYTHONPATH lets
# run_control_loop.py and the spawned policy worker import endpoint_adapter by name.
ADAPTER="--mount type=bind,source=$BASE/shared,target=/standin/shared,readonly -e PYTHONPATH=/standin/shared"
FACTORY="--policy-factory endpoint_adapter:make_policy"
# Episode files go into the volume (a Linux filesystem) through Roshan's own --output option.
# With his default (output/ on the /mnt/c mount) the supervisor failed here with
# "OSError: [Errno 61] No data available" while reading the growing policy_requests.jsonl.
LOOP="python3 scripts/run_control_loop.py --output runtime/output/control_loop"

step=$1
shift
case "$step" in
  build)
    docker build -t $IMAGE $BASE/team-d
    exit ;;
  prepare)
    docker run --rm $MOUNTS $IMAGE python3 scripts/prepare_control_loop_runtime.py
    exit ;;
  roshan)
    label=$1; shift
    code=0
    docker run --rm $MOUNTS $IMAGE $LOOP "$@" || code=$? ;;
  inside)
    label=$1; policy=$2; shift 2
    code=0
    # One container: start the server in the background, wait until /health answers, run the loop.
    # 127.0.0.1 inside the container is the container itself, so the adapter's default URL works.
    # The container ends when the loop ends, which also stops the server.
    docker run --rm $MOUNTS $ADAPTER \
      --mount type=bind,source=$BASE/team-c,target=/standin/team-c,readonly \
      $IMAGE sh -c '
        policy=$1; shift
        mkdir -p runtime/output/standin_eval
        python3 /standin/team-c/standin_infer/server.py --policy "$policy" \
          > "runtime/output/standin_eval/server-$policy.log" 2>&1 &
        until python3 -c "import urllib.request as u; u.urlopen(\"http://127.0.0.1:8765/health\", timeout=1)" 2>/dev/null
        do sleep 0.2; done
        "$@"
      ' sh "$policy" $LOOP $FACTORY "$@" || code=$? ;;
  host)
    label=$1; shift
    code=0
    # --network host: the container shares WSL's network. WSL runs in mirrored networking mode,
    # where 127.0.0.1 also reaches servers listening on Windows.
    docker run --rm --network host $MOUNTS $ADAPTER $IMAGE $LOOP $FACTORY "$@" || code=$? ;;
  *)
    echo "unknown step: $step"; exit 2 ;;
esac

# run_control_loop.py exits 1 when case_passed is false. That is a recorded outcome, not a
# launcher error, so the evidence is still copied: a second short container copies the newest
# episode's four files out of the volume into shared/logs, unchanged.
docker run --rm $MOUNTS --mount type=bind,source=$BASE/shared/logs,target=/logs $IMAGE sh -c '
  latest=$(ls -td runtime/output/control_loop/*/ | grep -v _policy_workers | head -1)
  target=/logs/live_$1_$(basename "$latest")
  mkdir -p "$target"
  cp "$latest"result.json "$latest"trace.jsonl "$latest"trace.md "$latest"manifest.json "$target"/
  echo "{\"source\": \"standin\", \"label\": \"$1\", \"step\": \"$2\", \"loop_args\": \"$4\", \"loop_exit_code\": $3}" > "$target"/standin.json
  # The endpoint log holds the glue-rule lines that metrics.py counts. Only the "inside" step
  # has it in the volume. For "host", save the Windows server output as server.log by hand.
  if [ -n "$5" ]; then cp "runtime/output/standin_eval/server-$5.log" "$target"/server.log; fi
  echo "run_control_loop.py exit code: $3; evidence copied to shared/logs/$(basename "$target")"
' sh "$label" "$step" "$code" "$*" "${policy:-}"
