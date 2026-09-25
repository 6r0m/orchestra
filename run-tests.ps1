# The host suite on Windows: powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1 [test ...]
# The modules that exercise a Windows host, in this checkout's own uv-managed Windows environment
# (app\foundation\envpath.py), which `uv sync --locked` creates or updates. The whole suite runs on
# WSL (run-tests.sh). Named tests replace the list.
param([Parameter(ValueFromRemainingArguments)][string[]] $Tests)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"

$hostTests = @(
    "tests.agents.test_launch", "tests.agents.test_terminal", "tests.agents.test_trust",
    "tests.workspace.test_repos", "tests.workspace.test_worktrees",
    "tests.orchestration.test_workflow", "tests.orchestration.test_stops", "tests.orchestration.test_replay",
    "tests.observability.test_trace_parity", "tests.observability.test_stale_settings", "tests.foundation.test_policy",
    "tests.foundation.test_flows",
    "tests.application.test_stack", "tests.test_architecture", "tests.test_harness"
)
if (-not $Tests) { $Tests = $hostTests }

# Native tools write progress to stderr; only their exit codes decide.
$ErrorActionPreference = "Continue"
$environment = (& $uv run --no-project --managed-python --python 3.13 python (Join-Path $here "app\foundation\envpath.py") $here 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $environment) { throw "could not derive this checkout's environment" }
$env:UV_PROJECT_ENVIRONMENT = $environment
& $uv --project $here sync --locked --quiet
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Push-Location $here
try {
    # Each test class in a process of its own, a few at a time (tests\runner.py).
    & $uv --project $here run --locked --no-sync python -m tests --parallel @Tests
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
