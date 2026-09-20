[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [switch]$SkipPull,
    [switch]$SkipDependencies,
    [switch]$SkipTests,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    $RepositoryRoot = Split-Path -Parent $scriptDirectory
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,

        [Parameter(ValueFromRemainingArguments)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Restore-TemporaryStash {
    param(
        [Parameter(Mandatory)]
        [string]$Root,

        [Parameter(Mandatory)]
        [string]$Marker
    )

    $stashRef = (& git -C $Root stash list --format="%gd %s" | Select-String -SimpleMatch $Marker | Select-Object -First 1).Line
    if (-not $stashRef) {
        throw "Unable to find the temporary stash '$Marker'. Run 'git stash list' before making more changes."
    }

    $stashName = ($stashRef -split " ", 2)[0]
    Invoke-CheckedCommand git -C $Root stash pop $stashName
}

$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$gitTopLevel = (& git -C $RepositoryRoot rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $gitTopLevel) {
    throw "Not a Git repository: $RepositoryRoot"
}
$gitTopLevel = (Resolve-Path -LiteralPath $gitTopLevel.Trim()).Path
if ($gitTopLevel -ne $RepositoryRoot) {
    throw "RepositoryRoot must be the Git top-level directory: $gitTopLevel"
}

if (-not $SkipPull) {
    $branch = (& git -C $RepositoryRoot branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $branch) {
        throw "The repository must be on a branch before pulling updates."
    }

    & git -C $RepositoryRoot rev-parse --abbrev-ref --symbolic-full-name '@{u}' *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Branch '$branch' has no upstream. Configure it before running this script."
    }

    $dirty = [bool](& git -C $RepositoryRoot status --porcelain)
    $stashMarker = "dm31-windows-build-$([guid]::NewGuid().ToString('N'))"
    $stashCreated = $false
    $pullError = $null

    if ($dirty) {
        Write-Host "Saving local changes to a temporary stash..."
        Invoke-CheckedCommand git -C $RepositoryRoot stash push --include-untracked -m $stashMarker
        $stashCreated = $true
    }

    try {
        Write-Host "Pulling '$branch' with fast-forward only..."
        Invoke-CheckedCommand git -C $RepositoryRoot pull --ff-only
    }
    catch {
        $pullError = $_
    }
    finally {
        if ($stashCreated) {
            Write-Host "Restoring local changes..."
            Restore-TemporaryStash -Root $RepositoryRoot -Marker $stashMarker
        }
    }

    if ($pullError) {
        throw $pullError
    }
}

$hostRoot = Join-Path $RepositoryRoot "QT_Host"
if (-not (Test-Path -LiteralPath $hostRoot -PathType Container)) {
    if ($SkipDependencies -and $SkipTests -and $SkipBuild) {
        Write-Host "Git update completed."
        exit 0
    }
    throw "QT_Host was not found under '$RepositoryRoot'."
}

$macMetadata = Get-ChildItem -LiteralPath $hostRoot -Recurse -Force -File |
    Where-Object { $_.Name -eq ".DS_Store" -or $_.Name -like "._*" }
foreach ($item in $macMetadata) {
    Remove-Item -LiteralPath $item.FullName -Force
}
if ($macMetadata) {
    Write-Host "Removed $($macMetadata.Count) macOS metadata file(s)."
}

$venvRoot = Join-Path $hostRoot ".venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    $systemPython = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($systemPython) {
        Invoke-CheckedCommand $systemPython.Source -m venv $venvRoot
    }
    else {
        $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
        if (-not $pyLauncher) {
            throw "Python was not found. Install 64-bit Python 3.13 or newer and retry."
        }
        Invoke-CheckedCommand $pyLauncher.Source -m venv $venvRoot
    }
}

if (-not $SkipDependencies) {
    Write-Host "Installing/updating Python dependencies..."
    Invoke-CheckedCommand $venvPython -m pip install -r (Join-Path $hostRoot "requirements.txt")
    Invoke-CheckedCommand $venvPython -m pip install "Nuitka==4.2.1" ordered-set zstandard
}

$previousQtPlatform = $env:QT_QPA_PLATFORM
$previousPythonPath = $env:PYTHONPATH
$previousVirtualEnv = $env:VIRTUAL_ENV
try {
    $env:QT_QPA_PLATFORM = "offscreen"
    $env:PYTHONPATH = "$hostRoot;$RepositoryRoot\Linux_ROS_WS\src\stm32_jetson_serial_comm"

    if (-not $SkipTests) {
        Write-Host "Running source smoke test and unit tests..."
        Invoke-CheckedCommand $venvPython (Join-Path $hostRoot "main.py") --smoke-test
        Invoke-CheckedCommand $venvPython -m unittest discover -s (Join-Path $hostRoot "tests")
    }

    if (-not $SkipBuild) {
        $deployTool = Join-Path $venvRoot "Scripts\pyside6-deploy.exe"
        $deployTemplate = Join-Path $hostRoot "pysidedeploy.windows.spec"
        $deploySpec = Join-Path $hostRoot ".pysidedeploy.windows.local.spec"
        $outputExe = Join-Path $hostRoot "dist\DM3.1 STM32 Debug Host.exe"
        if (-not (Test-Path -LiteralPath $deployTool -PathType Leaf)) {
            throw "pyside6-deploy.exe was not installed in the virtual environment."
        }
        if (-not (Test-Path -LiteralPath $deployTemplate -PathType Leaf)) {
            throw "Windows deployment spec was not found: $deployTemplate"
        }

        Copy-Item -LiteralPath $deployTemplate -Destination $deploySpec -Force

        if (Test-Path -LiteralPath $outputExe) {
            Remove-Item -LiteralPath $outputExe -Force
        }

        Write-Host "Building Windows executable..."
        $env:VIRTUAL_ENV = $venvRoot
        Push-Location $hostRoot
        try {
            Invoke-CheckedCommand $deployTool -c $deploySpec
        }
        finally {
            Pop-Location
            if (Test-Path -LiteralPath $deploySpec) {
                Remove-Item -LiteralPath $deploySpec -Force
            }
        }

        if (-not (Test-Path -LiteralPath $outputExe -PathType Leaf)) {
            throw "Build command finished without creating '$outputExe'."
        }

        $smokeProcess = Start-Process -FilePath $outputExe -ArgumentList "--smoke-test" -WindowStyle Hidden -Wait -PassThru
        if ($smokeProcess.ExitCode -ne 0) {
            throw "Packaged executable smoke test failed with exit code $($smokeProcess.ExitCode)."
        }

        $outputFile = Get-Item -LiteralPath $outputExe
        $outputHash = Get-FileHash -LiteralPath $outputExe -Algorithm SHA256
        Write-Host "Build complete."
        Write-Host "Path: $($outputFile.FullName)"
        Write-Host "Bytes: $($outputFile.Length)"
        Write-Host "SHA256: $($outputHash.Hash)"
    }
}
finally {
    $env:QT_QPA_PLATFORM = $previousQtPlatform
    $env:PYTHONPATH = $previousPythonPath
    $env:VIRTUAL_ENV = $previousVirtualEnv
}
