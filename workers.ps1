# Start or stop the Windows worker: powershell -File workers.ps1 up | down
# It runs in this checkout's uv-managed Windows environment (app\foundation\envpath.py) and records
# its pid in tmp\orchestration\worker-windows.pid. Called by workers.sh.
param([ValidateSet("up", "down")][string] $Action)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = $here
$runtime = Join-Path $repo "tmp\orchestration"
$pidFile = Join-Path $runtime "worker-windows.pid"
$uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null

function Get-Worker {
    if (-not (Test-Path $pidFile)) { return $null }
    $process = Get-Process -Id ([int](Get-Content $pidFile)) -ErrorAction SilentlyContinue
    if ($process -and $process.ProcessName -eq "python") { return $process }
    return $null
}

if ($Action -eq "up") {
    $running = Get-Worker
    if ($running) { "windows worker already running (pid $($running.Id))"; exit 0 }
    $ErrorActionPreference = "Continue"
    $environment = (& $uv run --no-project --managed-python --python 3.13 python (Join-Path $here "app\foundation\envpath.py") $repo 2>$null)
    $env:UV_PROJECT_ENVIRONMENT = $environment
    cmd /c "`"$uv`" --project `"$here`" sync --locked --quiet 2>&1"
    # Created by WMI rather than as this shell's child: a child would keep the WSL
    # session that launched this script open for as long as the worker lives. A process
    # WMI creates does not get the user's PATH, which the agents' hooks need for uv.
    $path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    $command = "cmd /c set `"PATH=$path`" && set `"UV_PROJECT_ENVIRONMENT=$environment`" && " +
               "`"$uv`" --project `"$here`" run --locked --no-sync python -m app.interfaces.worker windows >> `"$runtime\worker-windows.log`" 2>&1" +
               # However the worker ends — including killed from outside, which leaves no output of its own —
               # the log gains a line with when and with what exit code; `call` expands the values then.
               " & call echo worker exited at %^DATE% %^TIME% rc=%^ERRORLEVEL% >> `"$runtime\worker-windows.log`""
    # Hidden: the worker is a service, and a console WMI creates is otherwise shown — handed to Windows
    # Terminal where that is the default — taking focus, and closing that window would end the worker.
    $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
    $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create `
        -Arguments @{ CommandLine = $command; CurrentDirectory = $here; ProcessStartupInformation = $startup }
    if ($created.ReturnValue -ne 0) { throw "starting the windows worker failed: $($created.ReturnValue)" }
    "windows worker started; log: $runtime\worker-windows.log"
} else {
    $running = Get-Worker
    if ($running) {
        Stop-Process -Id $running.Id -Force
        Remove-Item $pidFile -ErrorAction SilentlyContinue
        "windows worker stopped"
    }
}
