$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptUnderTest = Join-Path $PSScriptRoot "..\update_and_build_windows.ps1"
if (-not (Test-Path -LiteralPath $scriptUnderTest -PathType Leaf)) {
    throw "Missing production script: $scriptUnderTest"
}

function Invoke-Git {
    param(
        [Parameter(Mandatory)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory, ValueFromRemainingArguments)]
        [string[]]$Arguments
    )

    & git -C $WorkingDirectory @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git failed in '$WorkingDirectory': git $($Arguments -join ' ')"
    }
}

function Assert-Equal {
    param(
        [Parameter(Mandatory)]$Expected,
        [Parameter(Mandatory)]$Actual,
        [Parameter(Mandatory)][string]$Message
    )

    if ($Expected -ne $Actual) {
        throw "$Message Expected '$Expected', got '$Actual'."
    }
}

$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("dm31-build-test-" + [guid]::NewGuid().ToString("N"))
$remote = Join-Path $testRoot "origin.git"
$mac = Join-Path $testRoot "mac"
$windows = Join-Path $testRoot "windows"

try {
    New-Item -ItemType Directory -Path $testRoot | Out-Null
    & git init --bare $remote | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to create bare test repository." }

    & git init $mac | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to create Mac fixture repository." }
    Invoke-Git $mac config user.name "DM31 Test"
    Invoke-Git $mac config user.email "dm31-test@example.invalid"
    Set-Content -LiteralPath (Join-Path $mac "app.txt") -Value "base"
    Invoke-Git $mac add app.txt
    Invoke-Git $mac commit -m "initial"
    Invoke-Git $mac branch -M main
    Invoke-Git $mac remote add origin $remote
    Invoke-Git $mac push -u origin main
    & git --git-dir=$remote symbolic-ref HEAD refs/heads/main
    if ($LASTEXITCODE -ne 0) { throw "Unable to set the bare repository HEAD." }

    & git clone $remote $windows | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to clone Windows fixture repository." }
    Invoke-Git $windows config user.name "DM31 Test"
    Invoke-Git $windows config user.email "dm31-test@example.invalid"

    Set-Content -LiteralPath (Join-Path $windows "app.txt") -Value "local change"
    Set-Content -LiteralPath (Join-Path $windows "local-untracked.txt") -Value "keep me"
    $fixtureHost = Join-Path $windows "QT_Host"
    New-Item -ItemType Directory -Path $fixtureHost | Out-Null
    $fixtureScript = Join-Path $fixtureHost "update_and_build_windows.ps1"
    Copy-Item -LiteralPath $scriptUnderTest -Destination $fixtureScript

    Set-Content -LiteralPath (Join-Path $mac "remote-update.txt") -Value "from mac"
    Invoke-Git $mac add remote-update.txt
    Invoke-Git $mac commit -m "mac update"
    Invoke-Git $mac push

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $fixtureScript `
        -SkipDependencies `
        -SkipTests `
        -SkipBuild
    if ($LASTEXITCODE -ne 0) {
        throw "Update script exited with code $LASTEXITCODE."
    }

    Assert-Equal "local change" ((Get-Content -Raw (Join-Path $windows "app.txt")).Trim()) "Tracked local changes were not restored."
    Assert-Equal "keep me" ((Get-Content -Raw (Join-Path $windows "local-untracked.txt")).Trim()) "Untracked local files were not restored."
    Assert-Equal "from mac" ((Get-Content -Raw (Join-Path $windows "remote-update.txt")).Trim()) "Remote update was not pulled."
    Assert-Equal "" ((& git -C $windows stash list) -join "`n") "Temporary stash was not removed after restoration."

    Write-Output "PASS: dirty working tree is restored after a fast-forward pull"
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
