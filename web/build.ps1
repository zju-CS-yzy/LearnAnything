cd "D:\MyCS\AI\Project\LearnAnything\web"

# 安装依赖
npm install 2>&1 | Select-Object -Last 10

Write-Host ""
Write-Host "=== 安装后 node_modules 是否存在 ==="
Test-Path "node_modules"

Write-Host ""
Write-Host "=== 构建 ==="
npx vite build --outDir dist --emptyOutDir 2>&1 | Select-Object -Last 15

Write-Host ""
Write-Host "=== 构建产物 ==="
Get-ChildItem -Path "dist" | Select-Object Name
Get-ChildItem -Path "dist\assets" -Filter "index-*.js" | Select-Object Name, LastWriteTime