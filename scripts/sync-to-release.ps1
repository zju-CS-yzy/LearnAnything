# sync-to-release.ps1
# LearnAnything-Dev -> LearnAnything (Release) 同步脚本
# 用法: cd LearnAnything-Dev; .\scripts\sync-to-release.ps1 [-Push]
#
# 说明:
#   此脚本将 Dev 仓库中的产品级文件同步到 Release 仓库。
#   默认只执行同步，不执行 git push（需要用户手动确认后推送）。
#   如需自动推送，添加 -Push 参数。

param(
    [switch]$Push = $false
)

# ========== 配置 ==========
$DevDir    = "D:\MyCS\AI\Project\LearnAnything-Dev"
$ReleaseDir = "D:\MyCS\AI\Project\LearnAnything"

# 核心目录（从 Dev 复制到 Release）
# LA-051-STRUCT-FIX: 移除 subjects（Dev 中已删除）
$CoreDirs = @(
    "agents",
    "app",
    "core",
    "config",
    "interfaces",
    "tests",
    "web",
    "web-vue"
)

# 根目录产品级文件
$RootFiles = @(
    "app.py",
    "requirements.txt",
    "README.md",
    "LICENSE"
)

# Dev-only 排除文件（robocopy /XF 参数）
$ExcludeFiles = @(
    "API.txt",
    "PROJECT_STATUS.md",
    "app.spec",
    "*.pyc"
)

# 排除目录（robocopy /XD 参数）
# LA-051-STRUCT-FIX: 添加 data（Dev 的本地数据不应复制到 Release）
$ExcludeDirs = @(
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "data",           # <-- LA-051-STRUCT-FIX: 排除 Dev 的 data/ 目录
    "dist",           # 排除构建产物
    "web-vue\dist",   # 排除前端构建产物
    "web\dist"        # 排除旧构建产物
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  LearnAnything Sync: Dev -> Release" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Dev:    $DevDir" -ForegroundColor Gray
Write-Host "Release: $ReleaseDir" -ForegroundColor Gray
Write-Host ""

# ========== 步骤1: 同步核心目录 ==========
Write-Host "[Step 1/4] 同步核心目录..." -ForegroundColor Yellow

foreach ($dir in $CoreDirs) {
    $src = Join-Path $DevDir $dir
    $dst = Join-Path $ReleaseDir $dir

    if (-not (Test-Path $src)) {
        Write-Host "  [SKIP] $dir (源目录不存在)" -ForegroundColor DarkGray
        continue
    }

    # 确保目标目录存在
    if (-not (Test-Path $dst)) {
        New-Item -ItemType Directory -Path $dst -Force | Out-Null
    }

    # 构建 robocopy 参数数组
    $robocopyArgs = @(
        $src,
        $dst,
        "/MIR",      # 镜像同步
        "/MT:8",     # 多线程
        "/NJH",      # 隐藏作业头
        "/NJS",      # 隐藏作业摘要
        "/NP",       # 隐藏进度
        "/NDL"       # 隐藏目录列表
    )

    # 添加文件排除
    foreach ($xf in $ExcludeFiles) {
        $robocopyArgs += "/XF"
        $robocopyArgs += $xf
    }

    # 添加目录排除
    foreach ($xd in $ExcludeDirs) {
        $robocopyArgs += "/XD"
        $robocopyArgs += $xd
    }

    # 执行 robocopy
    $proc = Start-Process -FilePath "robocopy" -ArgumentList $robocopyArgs -Wait -PassThru -WindowStyle Hidden -NoNewWindow

    # robocopy 退出码: 0-7 表示成功（0=无变化, 1-7=有文件被复制/跳过等）
    if ($proc.ExitCode -le 7) {
        Write-Host "  [OK] $dir" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] $dir (exit code: $($proc.ExitCode))" -ForegroundColor Yellow
    }
}

# ========== 步骤2: 同步特殊目录 ==========
Write-Host "`n[Step 2/4] 同步特殊目录..." -ForegroundColor Yellow

# docs/: 只保留 DESIGN.md 和 PROJECT_PAPER.md
$docsSrc = Join-Path $DevDir "docs"
$docsDst = Join-Path $ReleaseDir "docs"
if (Test-Path $docsSrc) {
    if (-not (Test-Path $docsDst)) {
        New-Item -ItemType Directory -Path $docsDst -Force | Out-Null
    }
    # 删除 Release docs 中现有内容
    Get-ChildItem $docsDst -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
    # 复制指定文件
    foreach ($f in @("DESIGN.md", "PROJECT_PAPER.md")) {
        $srcFile = Join-Path $docsSrc $f
        if (Test-Path $srcFile) {
            Copy-Item $srcFile $docsDst -Force
            Write-Host "  [OK] docs\$f" -ForegroundColor Green
        }
    }
}

# scripts/: 只保留构建脚本和同步脚本本身
$scriptsSrc = Join-Path $DevDir "scripts"
$scriptsDst = Join-Path $ReleaseDir "scripts"
if (Test-Path $scriptsSrc) {
    if (-not (Test-Path $scriptsDst)) {
        New-Item -ItemType Directory -Path $scriptsDst -Force | Out-Null
    }
    Get-ChildItem $scriptsDst -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
    # 复制允许的脚本
    $allowedScripts = @("build.bat", "sync-to-release.ps1", "build.ps1")
    foreach ($s in $allowedScripts) {
        $srcFile = Join-Path $scriptsSrc $s
        if (Test-Path $srcFile) {
            Copy-Item $srcFile $scriptsDst -Force
            Write-Host "  [OK] scripts\$s" -ForegroundColor Green
        }
    }
}

# knowledge_base/: 只保留 .gitkeep
$kbSrc = Join-Path $DevDir "knowledge_base"
$kbDst = Join-Path $ReleaseDir "knowledge_base"
if (-not (Test-Path $kbDst)) {
    New-Item -ItemType Directory -Path $kbDst -Force | Out-Null
}
# 保留 .gitkeep，删除其他内容
Get-ChildItem $kbDst -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne ".gitkeep" } | Remove-Item -Recurse -Force
if (-not (Test-Path (Join-Path $kbDst ".gitkeep"))) {
    New-Item -ItemType File -Path (Join-Path $kbDst ".gitkeep") -Force | Out-Null
}
Write-Host "  [OK] knowledge_base\.gitkeep" -ForegroundColor Green

# ========== 步骤3: 同步根目录文件 ==========
Write-Host "`n[Step 3/4] 同步根目录文件..." -ForegroundColor Yellow

foreach ($f in $RootFiles) {
    $srcFile = Join-Path $DevDir $f
    if (Test-Path $srcFile) {
        Copy-Item $srcFile $ReleaseDir -Force
        Write-Host "  [OK] $f" -ForegroundColor Green
    }
}

# 同步 Release 专用的 .gitignore
$gitignoreSrc = Join-Path $DevDir ".gitignore-release"
$gitignoreDst = Join-Path $ReleaseDir ".gitignore"
if (Test-Path $gitignoreSrc) {
    Copy-Item $gitignoreSrc $gitignoreDst -Force
    Write-Host "  [OK] .gitignore (Release 专用)" -ForegroundColor Green
} else {
    Write-Host "  [WARN] .gitignore-release 不存在，使用 Dev 的 .gitignore" -ForegroundColor Yellow
    Copy-Item (Join-Path $DevDir ".gitignore") $gitignoreDst -Force
}

# ========== 步骤4: Git 操作 ==========
Write-Host "`n[Step 4/4] Git 操作..." -ForegroundColor Yellow

Push-Location $ReleaseDir

try {
    # 检查 git 状态
    $status = git status --short 2>$null
    if ($status) {
        Write-Host "  检测到变更，准备提交..." -ForegroundColor Gray
        git add -A
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
        git commit -m "Sync from Dev @ $timestamp`n`nAuto-sync by sync-to-release.ps1"
        Write-Host "  [OK] Git commit 完成" -ForegroundColor Green

        if ($Push) {
            Write-Host "  正在推送到远程..." -ForegroundColor Gray
            git push origin main
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  [OK] Git push 完成" -ForegroundColor Green
            } else {
                Write-Host "  [ERROR] Git push 失败" -ForegroundColor Red
            }
        } else {
            Write-Host "`n  [INFO] 未使用 -Push 参数，跳过 git push" -ForegroundColor Cyan
            Write-Host "         请手动执行: git push origin main" -ForegroundColor Cyan
        }
    } else {
        Write-Host "  [INFO] 无变更，无需提交" -ForegroundColor Gray
    }
} finally {
    Pop-Location
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  同步完成！" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
