# One Windows worker, for the stack owner through workers.sh:
#   powershell -File workers.ps1 start|stop|status|sweep <name> [the pid a sweep knows is gone]
# <name> is the worker's name on this machine: its pid file and log in tmp\orchestration. It runs
# this checkout's own policy, in this checkout's uv-managed Windows environment (app\foundation\envpath.py).
param([ValidateSet("start", "stop", "status", "sweep")][string] $Action, [Parameter(Mandatory)][string] $Name,
      [string] $Gone = "")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtime = Join-Path $here "tmp\orchestration"
$pidFile = Join-Path $runtime "$Name.pid"
$log = Join-Path $runtime "$Name.log"
$uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null

function Get-Worker {
    # The process its pid file names while that is still this worker: the file outlives a killed
    # worker, and Windows reuses pids. A process of a higher integrity hides its command line; one
    # named python there is taken for the worker, so that it is never started twice.
    if (-not (Test-Path $pidFile)) { return $null }
    $id = 0
    if (-not [int]::TryParse(([string](Get-Content -Raw $pidFile)).Trim(), [ref] $id)) { return $null }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $id"
    if (-not $process) { return $null }
    if ($process.CommandLine -like "*-m app.interfaces.worker windows*") { return $process }
    if ($null -eq $process.CommandLine -and $process.Name -eq "python.exe") { return $process }
    return $null
}

function Test-Elevated {
    $principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Use-Environment {
    # Native tools write progress to stderr; only their exit codes decide.
    $ErrorActionPreference = "Continue"
    $environment = (& $uv run --no-project --managed-python --python 3.13 python (Join-Path $here "app\foundation\envpath.py") $here 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $environment) { throw "could not derive this checkout's environment" }
    $env:UV_PROJECT_ENVIRONMENT = $environment
    return $environment
}

switch ($Action) {
    "status" {
        $worker = Get-Worker
        if ($worker) { "running $($worker.ProcessId)" } else { "stopped" }
        # Whether a start from here would be refused, so no one stops a worker only to find that out.
        if (Test-Elevated) { "elevated" }
    }
    "start" {
        $worker = Get-Worker
        if ($worker) { "running $($worker.ProcessId)"; exit 0 }
        # WSL runs Windows programs with the token of whatever started it; from an elevated one, the
        # worker and every agent it starts would run as an administrator.
        if (Test-Elevated) {
            "refused: Windows programs started from here run elevated, because WSL was started by an " +
            "elevated process, and the Windows worker and its agents never run as an administrator. Start " +
            "WSL from a normal terminal (wsl --shutdown, then open WSL), or start the worker from one."
            exit 1
        }
        $environment = Use-Environment
        $ErrorActionPreference = "Continue"
        cmd /c "`"$uv`" --project `"$here`" sync --locked --quiet 2>&1"
        # Created by WMI rather than as this shell's child: a child would keep the WSL session that
        # launched this script open for as long as the worker lives. A process WMI creates does not
        # get the user's PATH, which the agents' hooks need for uv.
        $path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
        $command = "cmd /c set `"PATH=$path`" && set `"UV_PROJECT_ENVIRONMENT=$environment`" && " +
                   "`"$uv`" --project `"$here`" run --locked --no-sync python -m app.interfaces.worker windows >> `"$log`" 2>&1" +
                   # However the worker ends — including killed from outside, which leaves no output of its own —
                   # the log gains a line with when and with what exit code; `call` expands the values then.
                   " & call echo worker exited at %^DATE% %^TIME% rc=%^ERRORLEVEL% >> `"$log`""
        # Its temporary folder is named, so the sweep after its stop looks where its stages wrote.
        $command = "cmd /c set `"TEMP=$env:TEMP`" && set `"TMP=$env:TEMP`" && " + $command.Substring(7)
        # Hidden: the worker is a service, and a console WMI creates is otherwise shown — handed to Windows
        # Terminal where that is the default — taking focus, and closing that window would end the worker.
        $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
        $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create `
            -Arguments @{ CommandLine = $command; CurrentDirectory = $here; ProcessStartupInformation = $startup }
        if ($created.ReturnValue -ne 0) { throw "starting the windows worker failed: $($created.ReturnValue)" }
        "started; log: $log"
    }
    "stop" {
        $worker = Get-Worker
        if ($worker) {
            Stop-Process -Id $worker.ProcessId -Force
            $deadline = (Get-Date).AddSeconds(10)
            while ((Get-Worker) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 300 }
            $worker = Get-Worker
            if ($worker) { "still running $($worker.ProcessId)"; exit 1 }
        }
        Remove-Item $pidFile -ErrorAction SilentlyContinue
        "stopped"
    }
    "sweep" {
        Use-Environment | Out-Null
        $ErrorActionPreference = "Continue"
        Push-Location $here
        try {
            if ($Gone) { & $uv --project $here run --locked --no-sync python -m app.interfaces.worker sweep $Gone }
            else { & $uv --project $here run --locked --no-sync python -m app.interfaces.worker sweep }
            exit $LASTEXITCODE
        } finally {
            Pop-Location
        }
    }
}
