<#
.SYNOPSIS
    Prove that a version rollout serves every request.

.DESCRIPTION
    Builds a new backend image tag, side-loads it, then rolls it out through
    Terraform (the same path a real deploy takes) while hammering the health
    endpoint through the Ingress. Every response code is counted; a single
    non-200 makes the run fail.

    The probe deliberately goes through the Ingress rather than a port-forward:
    a port-forward talks to one pod and would hide exactly the endpoint churn
    this test is meant to catch.

.EXAMPLE
    ./scripts/proof-zero-downtime.ps1 -NewTag v2
#>
[CmdletBinding()]
param(
    [string]$NewTag = "v2",
    [string]$Url = "http://docuchat.localtest.me:8080/api/healthz",
    [int]$IntervalMs = 100,
    [string]$ClusterName = "shipyard",
    [string]$OutFile
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$tf = Join-Path $repo "terraform"
$kubeconfig = Join-Path $tf "kubeconfig"
$apiImage = "shipyard/docuchat-api:$NewTag"

# Invoke-Native lives in _common.ps1: docker, kind and terraform write progress
# to stderr, which Windows PowerShell treats as a terminating error under
# $ErrorActionPreference=Stop.
. (Join-Path $PSScriptRoot "_common.ps1")

Write-Host "=== Building $apiImage ===" -ForegroundColor Cyan
Invoke-Native docker @('build', '-t', $apiImage, '--build-arg', "APP_VERSION=$NewTag", (Join-Path $repo "app\backend"))

Write-Host "=== Loading into kind ===" -ForegroundColor Cyan
Invoke-Native kind @('load', 'docker-image', $apiImage, '--name', $ClusterName)

# The rollout runs in the background so the probe loop can measure it live.
Write-Host "=== Rolling out via terraform apply ===" -ForegroundColor Cyan
$rollout = Start-Job -ScriptBlock {
    param($tfDir, $api)
    Set-Location $tfDir
    $a = @('apply', '-input=false', '-auto-approve', '-no-color',
        '-var', "api_image=$api", '-var', 'web_image=shipyard/docuchat-web:dev')
    & terraform @a 2>&1
} -ArgumentList $tf, $apiImage

$total = 0; $ok = 0; $fail = 0
$codes = @{}
$failures = New-Object System.Collections.Generic.List[string]
$start = Get-Date

while ($rollout.State -eq "Running") {
    $total++
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
        $code = [int]$r.StatusCode
    }
    catch {
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        else { $code = 0 }   # connection refused / reset / timeout
    }
    if ($code -eq 200) { $ok++ } else {
        $fail++
        $failures.Add("$([DateTime]::Now.ToString('HH:mm:ss.fff')) code=$code")
    }
    if ($codes.ContainsKey($code)) { $codes[$code]++ } else { $codes[$code] = 1 }
    Start-Sleep -Milliseconds $IntervalMs
}

$elapsed = (Get-Date) - $start
$applyOutput = Receive-Job $rollout
Remove-Job $rollout

$report = @()
$report += "=== Zero-downtime rollout proof ==="
$report += "started      : $($start.ToString('yyyy-MM-dd HH:mm:ss'))"
$report += "probe url    : $Url"
$report += "probe every  : ${IntervalMs}ms"
$report += "new image    : $apiImage"
$report += "duration     : $([math]::Round($elapsed.TotalSeconds,1))s"
$report += "requests     : $total"
$report += "HTTP 200     : $ok"
$report += "failed       : $fail"
$report += "status codes : " + (($codes.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join " ")
if ($fail -gt 0) {
    $report += "failure log  :"
    $report += ($failures | Select-Object -First 20)
}
$report += ""
$report += "terraform tail:"
$report += ($applyOutput | Select-Object -Last 6)

$report | ForEach-Object { Write-Host $_ }

if ($OutFile) {
    $report | Out-File -FilePath $OutFile -Encoding utf8
    Write-Host "`nsaved to $OutFile"
}

if ($fail -gt 0) { exit 1 }
