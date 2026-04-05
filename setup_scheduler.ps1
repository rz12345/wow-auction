# 註冊 Windows 工作排程器 — WoW 拍賣場價格監控
# 執行方式：以系統管理員身份在 PowerShell 執行此腳本
#   .\setup_scheduler.ps1
# 若要更改執行間隔，修改 $IntervalHours 參數

param(
    [int]$IntervalHours = 4
)

$TaskName   = "WowAuctionMonitor"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python     = (Get-Command python).Source
$Script     = Join-Path $ProjectDir "start.py"
$LogFile    = Join-Path $ProjectDir "logs\scheduler.log"

# 建立 logs 目錄
New-Item -ItemType Directory -Force -Path (Join-Path $ProjectDir "logs") | Out-Null

# 若排程已存在先移除
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "已移除舊排程：$TaskName"
}

# 執行動作：python start.py，stdout/stderr 導向 log
$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$Python`" `"$Script`" >> `"$LogFile`" 2>&1" `
    -WorkingDirectory $ProjectDir

# 觸發條件：每日 00:00 起，每 N 小時重複，持續 24 小時
$Trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At "00:00" `
    -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) `
    -RepetitionDuration (New-TimeSpan -Hours 24)

# 設定：只要使用者已登入就執行，不需要密碼
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "每 $IntervalHours 小時執行一次 WoW 拍賣場價格監控" `
    -RunLevel Highest | Out-Null

Write-Host ""
Write-Host "排程已建立：$TaskName"
Write-Host "  Python  : $Python"
Write-Host "  腳本    : $Script"
Write-Host "  間隔    : 每 $IntervalHours 小時"
Write-Host "  Log     : $LogFile"
Write-Host ""
Write-Host "立即執行測試："
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "查看狀態："
Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
Write-Host "移除排程："
Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
