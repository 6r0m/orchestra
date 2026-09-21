# Press a Workbench button in headless Edge, for `make demo`:
#   powershell -File tools/demo_press.ps1 <workbench url> <run id> <button label> <expected action>
# Runs tools/demo_press.py in this checkout's uv-managed Windows environment (app\foundation\envpath.py).
param([string] $Url, [string] $Run, [string] $Label, [string] $Action)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"

# Native tools write progress to stderr; only their exit codes decide.
$ErrorActionPreference = "Continue"
$environment = (& $uv run --no-project --managed-python --python 3.13 python (Join-Path $repo "app\foundation\envpath.py") $repo 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $environment) { throw "could not derive this checkout's environment" }
$env:UV_PROJECT_ENVIRONMENT = $environment
& $uv --project $repo run --locked --quiet python (Join-Path $repo "tools\demo_press.py") $Url $Run $Label $Action
exit $LASTEXITCODE
