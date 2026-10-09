# ============================================================
# EventSentry —— Fly.io 一键部署脚本
# 前置：已注册 Fly.io 账号并完成 `flyctl auth login`
# 用法：在项目根目录执行  powershell -ExecutionPolicy Bypass -File deploy_fly.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$FLY = "D:\Zcode\tools\fly\flyctl.exe"
$APP = "eventsentry"

if (-not (Test-Path $FLY)) {
    Write-Host "❌ 未找到 flyctl：$FLY" -ForegroundColor Red
    exit 1
}

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " EventSentry → Fly.io 部署" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. 认证检查 ──
Write-Host "[1/6] 检查登录状态…" -ForegroundColor Yellow
& $FLY auth whoami 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) {
    Write-Host "请先执行： $FLY auth login" -ForegroundColor Red
    exit 1
}

# ── 2. 交互式选择区域并创建应用 ──
Write-Host ""
Write-Host "[2/6] 创建应用（如已存在会自动跳过）…" -ForegroundColor Yellow
& $FLY apps create $APP --org personal 2>&1 | Out-Host

# ── 3. 持久卷（存 SQLite；已存在会报错，忽略即可） ──
Write-Host ""
Write-Host "[3/6] 创建持久卷 eventsentry_data（1GB）…" -ForegroundColor Yellow
& $FLY volumes create eventsentry_data --size 1 --region hkg --yes 2>&1 | Out-Host

# ── 4. 密钥 ──
Write-Host ""
Write-Host "[4/6] 注入密钥" -ForegroundColor Yellow
if (-not $env:LLM_API_KEY)    { $env:LLM_API_KEY    = Read-Host "请输入 LLM_API_KEY（智谱 GLM，直接回车跳过）" }
if (-not $env:SERPER_API_KEY) { $env:SERPER_API_KEY = Read-Host "请输入 SERPER_API_KEY（直接回车跳过）" }

$secrets = @()
if ($env:LLM_API_KEY)    { $secrets += "LLM_API_KEY=$($env:LLM_API_KEY)" }
if ($env:SERPER_API_KEY) { $secrets += "SERPER_API_KEY=$($env:SERPER_API_KEY)" }
if ($secrets.Count -gt 0) {
    & $FLY secrets set @secrets --app $APP 2>&1 | Out-Host
} else {
    Write-Host "  未提供密钥，跳过（参谋对话与媒体采集将不可用）" -ForegroundColor DarkYellow
}

# ── 5. 部署 ──
Write-Host ""
Write-Host "[5/6] 开始部署（首次约 3-5 分钟）…" -ForegroundColor Yellow
& $FLY deploy --app $APP 2>&1 | Out-Host

# ── 6. 验收 ──
Write-Host ""
Write-Host "[6/6] 健康检查" -ForegroundColor Yellow
$url = "https://$APP.fly.dev"
Start-Sleep -Seconds 8
try {
    $r = Invoke-WebRequest -Uri "$url/api/ping" -TimeoutSec 30 -UseBasicParsing
    Write-Host "  ✅ $url/api/ping → HTTP $($r.StatusCode)" -ForegroundColor Green
    $e = Invoke-WebRequest -Uri "$url/api/events?limit=1" -TimeoutSec 30 -UseBasicParsing
    $n = ($e.Content | ConvertFrom-Json).total
    Write-Host "  ✅ 事件数: $n" -ForegroundColor Green
} catch {
    Write-Host "  ⚠️ 健康检查未通过：$_" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host " 部署完成！固定地址： $url" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
