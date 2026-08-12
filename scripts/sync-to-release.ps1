# LearnAnything-Dev -> LearnAnything (public Release) sync script
# Usage (from the Dev repository):
#   .\scripts\sync-to-release.ps1 -NoCommit   # sync and inspect first
#   .\scripts\sync-to-release.ps1 -Push       # sync, commit and push

[CmdletBinding()]
param(
    [switch]$Push,
    [switch]$NoCommit,
    [string]$DevDir = (Split-Path -Parent $PSScriptRoot),
    [string]$ReleaseDir = (Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "LearnAnything")
)

$ErrorActionPreference = "Stop"

if ($Push -and $NoCommit) {
    throw "-Push and -NoCommit cannot be used together."
}

function Resolve-RepositoryPath {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$ExpectedLeaf)

    $resolved = (Resolve-Path -LiteralPath $Path).Path.TrimEnd('\')
    if ((Split-Path -Leaf $resolved) -ne $ExpectedLeaf) {
        throw "Repository path must end with '$ExpectedLeaf': $resolved"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $resolved ".git"))) {
        throw "Not a Git repository: $resolved"
    }
    return $resolved
}

function Assert-PathWithin {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Root)

    $fullPath = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $fullRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    if (-not $fullPath.StartsWith($fullRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify a path outside the Release repository: $fullPath"
    }
}

function Invoke-RobocopyMirror {
    param([Parameter(Mandatory)][string]$Source, [Parameter(Mandatory)][string]$Destination)

    Assert-PathWithin -Path $Destination -Root $script:ReleaseDir
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    $arguments = @(
        $Source, $Destination, "/MIR", "/MT:8", "/NJH", "/NJS", "/NP", "/NDL",
        "/XF", "API.txt", "api_config.ini", "PROJECT_STATUS.md", "app.spec", "*.pyc",
        "/XD", ".git", ".pytest_cache", "__pycache__", "node_modules", "data", "dist"
    )
    $process = Start-Process -FilePath "robocopy" -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -gt 7) {
        throw "robocopy failed for '$Source' (exit code $($process.ExitCode))."
    }
}

function Sync-AllowListDirectory {
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][string]$Destination,
        [Parameter(Mandatory)][string[]]$AllowedFiles
    )

    Assert-PathWithin -Path $Destination -Root $script:ReleaseDir
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    foreach ($item in Get-ChildItem -LiteralPath $Destination -Force -ErrorAction SilentlyContinue) {
        if ($item.Name -notin $AllowedFiles) {
            Remove-Item -LiteralPath $item.FullName -Recurse -Force
        }
    }
    foreach ($name in $AllowedFiles) {
        $sourceFile = Join-Path $Source $name
        if (Test-Path -LiteralPath $sourceFile -PathType Leaf) {
            Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $Destination $name) -Force
            Write-Host "  [OK] $name" -ForegroundColor Green
        }
    }
}

function Test-ReleaseSafety {
    $changedFiles = @(
        git -C $script:ReleaseDir diff --name-only --diff-filter=ACMR HEAD
        git -C $script:ReleaseDir ls-files --others --exclude-standard
    ) | Where-Object { $_ } | Sort-Object -Unique

    $forbiddenPath = '(^|/)(API\.txt|\.env(?:\..*)?|[^/]*\.(?:key|pem))$|^config/api_config\.ini$'
    $secretPattern = '(?i)(sk-(?:proj-)?[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,})'

    foreach ($relativePath in $changedFiles) {
        $normalized = $relativePath.Replace('\', '/')
        if ($normalized -match $forbiddenPath) {
            throw "Sensitive file is present in the Release changes: $relativePath"
        }

        $fullPath = Join-Path $script:ReleaseDir $relativePath
        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) { continue }
        $lineNumber = 0
        foreach ($line in Get-Content -LiteralPath $fullPath -ErrorAction SilentlyContinue) {
            $lineNumber++
            if ($line -match $secretPattern) {
                throw "Possible credential detected at ${relativePath}:$lineNumber (value suppressed)."
            }
        }
    }
}

$script:DevDir = Resolve-RepositoryPath -Path $DevDir -ExpectedLeaf "LearnAnything-Dev"
$script:ReleaseDir = Resolve-RepositoryPath -Path $ReleaseDir -ExpectedLeaf "LearnAnything"
if ($script:DevDir -eq $script:ReleaseDir) { throw "Dev and Release paths must differ." }

$releaseRemote = (git -C $script:ReleaseDir remote get-url origin).Trim()
if ($LASTEXITCODE -ne 0 -or $releaseRemote -notmatch 'github\.com[:/]zju-CS-yzy/LearnAnything(?:\.git)?$') {
    throw "Unexpected Release origin: $releaseRemote"
}
if ((git -C $script:ReleaseDir branch --show-current).Trim() -ne "main") {
    throw "Release repository must be on branch 'main'."
}
if (git -C $script:ReleaseDir status --porcelain) {
    throw "Release repository has uncommitted changes. Commit or clean them before syncing."
}

$coreDirs = @("agents", "app", "config", "core", "interfaces", "tests", "web", "web-vue")
$rootFiles = @("app.py", "main.py", "app.spec", "rebuild.bat", "requirements.txt", "README.md", "LICENSE")
$publicDocs = @("DESIGN.md", "PROJECT_PAPER.md", "DEPLOY.md")
$publicScripts = @(
    "build.bat",
    "build-release.py",
    "build_uninstaller.py",
    "manage_admin.py",
    "sync-to-release.ps1",
    "uninstaller.py"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " LearnAnything: Dev -> public Release" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Dev:     $script:DevDir" -ForegroundColor Gray
Write-Host "Release: $script:ReleaseDir" -ForegroundColor Gray
Write-Host "Origin:  $releaseRemote" -ForegroundColor Gray

Write-Host "`n[1/4] Mirroring product directories..." -ForegroundColor Yellow
foreach ($directory in $coreDirs) {
    $source = Join-Path $script:DevDir $directory
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        Write-Host "  [SKIP] $directory" -ForegroundColor DarkGray
        continue
    }
    Invoke-RobocopyMirror -Source $source -Destination (Join-Path $script:ReleaseDir $directory)
    Write-Host "  [OK] $directory" -ForegroundColor Green
}

Write-Host "`n[2/4] Syncing public docs and scripts..." -ForegroundColor Yellow
Sync-AllowListDirectory -Source (Join-Path $script:DevDir "docs") -Destination (Join-Path $script:ReleaseDir "docs") -AllowedFiles $publicDocs
Sync-AllowListDirectory -Source (Join-Path $script:DevDir "scripts") -Destination (Join-Path $script:ReleaseDir "scripts") -AllowedFiles $publicScripts

Write-Host "`n[3/4] Syncing root files..." -ForegroundColor Yellow
foreach ($name in $rootFiles) {
    $sourceFile = Join-Path $script:DevDir $name
    if (Test-Path -LiteralPath $sourceFile -PathType Leaf) {
        Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $script:ReleaseDir $name) -Force
        Write-Host "  [OK] $name" -ForegroundColor Green
    }
}
$releaseGitignore = Join-Path $script:DevDir ".gitignore-release"
if (-not (Test-Path -LiteralPath $releaseGitignore -PathType Leaf)) {
    throw "Missing public Release ignore policy: $releaseGitignore"
}
Copy-Item -LiteralPath $releaseGitignore -Destination (Join-Path $script:ReleaseDir ".gitignore") -Force
Write-Host "  [OK] .gitignore (public Release policy)" -ForegroundColor Green

Write-Host "`n[4/4] Running public-release safety checks..." -ForegroundColor Yellow
Test-ReleaseSafety
Write-Host "  [OK] No forbidden files or common credential patterns found" -ForegroundColor Green

if ($NoCommit) {
    Write-Host "`nSync complete. Changes were not staged or committed (-NoCommit)." -ForegroundColor Cyan
    exit 0
}

git -C $script:ReleaseDir add -A
if ($LASTEXITCODE -ne 0) { throw "git add failed." }
$diffCheck = git -C $script:ReleaseDir diff --cached --check 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warning "The staged diff contains legacy whitespace warnings; review with 'git diff --cached --check'."
}

if (git -C $script:ReleaseDir diff --cached --quiet) {
    Write-Host "`nNo Release changes to commit." -ForegroundColor Gray
    exit 0
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
git -C $script:ReleaseDir commit -m "Sync accepted features from Dev @ $timestamp"
if ($LASTEXITCODE -ne 0) { throw "git commit failed." }

if ($Push) {
    git -C $script:ReleaseDir push origin main
    if ($LASTEXITCODE -ne 0) { throw "git push failed." }
    Write-Host "`nRelease commit pushed to origin/main." -ForegroundColor Green
} else {
    Write-Host "`nRelease commit created. Run 'git push origin main' after review." -ForegroundColor Cyan
}
