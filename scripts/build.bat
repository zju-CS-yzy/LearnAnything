# LearnAnything 构建脚本
# 功能：
# 1. 杀死占用端口 5001 的进程
# 2. 清理 dist 和 build 文件夹
# 3. 重新构建前端（Vue）
# 4. 重新构建后端（PyInstaller）

param(
    [switch]$SkipFrontend = $false,
    [switch]$SkipBackend = $false
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  LearnAnything 构建脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ===== 步骤1：杀死占用端口5001的进程 =====
Write-Host "[1/5] 检查并杀死占用端口 5001 的进程..." -ForegroundColor Yellow

try {
    $connections = netstat -ano | findstr 5001 | findstr LISTENING
    if ($connections) {
        $pids = @()
        foreach ($line in $connections -split "`r`n") {
            if ($line -match "\s+(\d+)\s*$") {
                $pid = $matches[1]
                if ($pid -and $pid -ne "0" -and $pids -notcontains $pid) {
                    $pids += $pid
                }
            }
        }
        
        foreach ($pid in $pids) {
            try {
                $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
                if ($proc) {
                    Write-Host "  正在终止进程: $($proc.ProcessName) (PID: $pid)" -ForegroundColor DarkYellow
                    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                    Write-Host "  ✓ 已终止" -ForegroundColor Green
                }
            } catch {
                Write-Host "  ⚠ 无法终止 PID $pid : $_" -ForegroundColor DarkYellow
            }
        }
    } else {
        Write-Host "  端口 5001 未被占用" -ForegroundColor Green
    }
} catch {
    Write-Host "  ⚠ 检查端口时出错: $_" -ForegroundColor DarkYellow
}

# 额外检查 python 进程（常见后端进程名）
$pythonProcs = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    try {
        $conns = Get-NetTCPConnection -OwningProcess $_.Id -LocalPort 5001 -ErrorAction SilentlyContinue
        $conns -and $conns.Count -gt 0
    } catch { $false }
}
foreach ($proc in $pythonProcs) {
    try {
        Write-Host "  正在终止 Python 进程 (PID: $($proc.Id))" -ForegroundColor DarkYellow
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Host "  ⚠ 无法终止 Python PID $($proc.Id)" -ForegroundColor DarkYellow
    }
}

Write-Host ""

# ===== 步骤2：清理 dist 和 build 文件夹 =====
Write-Host "[2/5] 清理构建产物..." -ForegroundColor Yellow

$dirsToClean = @(
    "dist",
    "build",
    "web-vue\dist"
)

foreach ($dir in $dirsToClean) {
    $fullPath = Join-Path $projectRoot $dir
    if (Test-Path $fullPath) {
        try {
            Remove-Item -Path $fullPath -Recurse -Force -ErrorAction Stop
            Write-Host "  ✓ 已删除: $dir" -ForegroundColor Green
        } catch {
            Write-Host "  ⚠ 无法删除 $dir : $_" -ForegroundColor DarkYellow
        }
    } else {
        Write-Host "  - 不存在: $dir" -ForegroundColor Gray
    }
}

Write-Host ""

# ===== 步骤3：构建前端 =====
if (-not $SkipFrontend) {
    Write-Host "[3/5] 构建前端 (Vue)..." -ForegroundColor Yellow
    
    $webVueDir = Join-Path $projectRoot "web-vue"
    if (Test-Path $webVueDir) {
        Set-Location $webVueDir
        
        try {
            # 检查 node_modules 是否存在
            if (-not (Test-Path (Join-Path $webVueDir "node_modules"))) {
                Write-Host "  安装依赖..." -ForegroundColor DarkYellow
                npm install 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
            }
            
            Write-Host "  运行 npm run build..." -ForegroundColor DarkYellow
            npm run build 2>&1 | ForEach-Object {
                $line = $_.ToString().Trim()
                if ($line -match "error|Error|ERROR|ERR!") {
                    Write-Host "    $line" -ForegroundColor Red
                } elseif ($line -match "warning|WARN|Warning") {
                    Write-Host "    $line" -ForegroundColor DarkYellow
                } else {
                    Write-Host "    $line" -ForegroundColor Gray
                }
            }
            
            # 检查构建是否成功
            $distDir = Join-Path $webVueDir "dist"
            if (Test-Path $distDir) {
                $indexHtml = Join-Path $distDir "index.html"
                if (Test-Path $indexHtml) {
                    Write-Host "  ✓ 前端构建成功" -ForegroundColor Green
                } else {
                    Write-Host "  ✗ 前端构建可能失败（缺少 index.html）" -ForegroundColor Red
                }
            } else {
                Write-Host "  ✗ 前端构建失败（缺少 dist 目录）" -ForegroundColor Red
            }
        } catch {
            Write-Host "  ✗ 前端构建出错: $_" -ForegroundColor Red
        }
        
        Set-Location $projectRoot
    } else {
        Write-Host "  ✗ 未找到 web-vue 目录" -ForegroundColor Red
    }
} else {
    Write-Host "[3/5] 跳过前端构建 (--SkipFrontend)" -ForegroundColor Gray
}

Write-Host ""

# ===== 步骤4：复制前端构建产物到 app 目录 =====
Write-Host "[4/5] 复制前端资源..." -ForegroundColor Yellow

$appStaticDir = Join-Path $projectRoot "app\static"
$webVueDist = Join-Path $projectRoot "web-vue\dist"

if (Test-Path $webVueDist) {
    # 确保 app/static 目录存在
    if (-not (Test-Path $appStaticDir)) {
        New-Item -ItemType Directory -Path $appStaticDir -Force | Out-Null
    }
    
    # 复制 dist 内容到 app/static
    try {
        Copy-Item -Path "$webVueDist\*" -Destination $appStaticDir -Recurse -Force -ErrorAction Stop
        Write-Host "  ✓ 前端资源已复制到 app/static" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ 复制失败: $_" -ForegroundColor Red
    }
} else {
    Write-Host "  ⚠ web-vue/dist 不存在，跳过复制" -ForegroundColor DarkYellow
}

Write-Host ""

# ===== 步骤5：构建后端（PyInstaller） =====
if (-not $SkipBackend) {
    Write-Host "[5/5] 构建后端 (PyInstaller)..." -ForegroundColor Yellow
    
    Set-Location $projectRoot
    
    try {
        # 检查 app.spec 是否存在
        $specFile = Join-Path $projectRoot "app.spec"
        if (-not (Test-Path $specFile)) {
            Write-Host "  ✗ 未找到 app.spec 文件" -ForegroundColor Red
            exit 1
        }
        
        Write-Host "  运行 pyinstaller app.spec..." -ForegroundColor DarkYellow
        pyinstaller app.spec --noconfirm 2>&1 | ForEach-Object {
            $line = $_.ToString().Trim()
            if ($line -match "error|Error|ERROR|ERR!") {
                Write-Host "    $line" -ForegroundColor Red
            } elseif ($line -match "warning|WARN|Warning") {
                Write-Host "    $line" -ForegroundColor DarkYellow
            } else {
                Write-Host "    $line" -ForegroundColor Gray
            }
        }
        
        # 检查构建是否成功
        $exePath = Join-Path $projectRoot "dist\LearnAnything\LearnAnything.exe"
        if (Test-Path $exePath) {
            $exeSize = (Get-Item $exePath).Length / 1MB
            Write-Host "  ✓ 后端构建成功" -ForegroundColor Green
            Write-Host "    输出: dist\LearnAnything\LearnAnything.exe ($([math]::Round($exeSize,1)) MB)" -ForegroundColor Green
        } else {
            Write-Host "  ✗ 后端构建失败（缺少 .exe 文件）" -ForegroundColor Red
        }
    } catch {
        Write-Host "  ✗ 后端构建出错: $_" -ForegroundColor Red
    }
} else {
    Write-Host "[5/5] 跳过后端构建 (--SkipBackend)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  构建完成！" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 返回项目根目录
Set-Location $projectRoot
