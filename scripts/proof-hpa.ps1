<#
.SYNOPSIS
    Drive real load at the API and record what the HPA does about it.

.DESCRIPTION
    Runs the k6 profile in scripts/load.js while sampling the HorizontalPodAutoscaler
    once a second. The sample log is the proof: replica count and measured CPU
    utilisation over time, from one pod up to whatever the load needs and back.

.EXAMPLE
    ./scripts/proof-hpa.ps1 -OutFile docs/proofs/hpa-scale.txt
#>
[CmdletBinding()]
param(
    [string]$BaseUrl = "http://docuchat.localtest.me:8080",
    [string]$Namespace = "docuchat",
    [string]$Hpa = "shipyard-docuchat-api",
    [string]$K6 = "C:\Program Files\k6\k6.exe",
    [string]$OutFile
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$env:KUBECONFIG = Join-Path $repo "terraform\kubeconfig"

if (-not (Test-Path $K6)) { throw "k6 not found at $K6 (winget install -e --id GrafanaLabs.k6)" }

Write-Host "=== Starting load ===" -ForegroundColor Cyan
$load = Start-Job -ScriptBlock {
    param($k6, $script, $base)
    & $k6 run -e "BASE_URL=$base" $script 2>&1
} -ArgumentList $K6, (Join-Path $PSScriptRoot "load.js"), $BaseUrl

$samples = New-Object System.Collections.Generic.List[string]
$samples.Add("time      replicas  cpu-target  ready-pods")
$peak = 0

while ($load.State -eq "Running") {
    $h = kubectl get hpa $Hpa -n $Namespace -o json 2>$null | ConvertFrom-Json
    if ($h) {
        $replicas = $h.status.desiredReplicas
        $current = $h.status.currentMetrics.resource.current.averageUtilization
        if ($null -eq $current) { $current = "n/a" }
        $ready = (kubectl get pods -n $Namespace -l app.kubernetes.io/component=api `
                --field-selector=status.phase=Running -o name | Measure-Object).Count
        if ($replicas -gt $peak) { $peak = $replicas }
        # Build the line first: commas inside a method call bind to the method's
        # argument list, not to the -f operator.
        $line = "{0}  {1,8}  {2,10}  {3,10}" -f (Get-Date -Format "HH:mm:ss"), $replicas, $current, $ready
        $samples.Add($line)
    }
    Start-Sleep -Seconds 1
}

$k6Output = Receive-Job $load
Remove-Job $load

$report = @()
$report += "=== HPA scale-out proof ==="
$report += "load profile : scripts/load.js (k6, POST /api/chat)"
$report += "hpa          : $Hpa (namespace $Namespace)"
$report += "peak replicas: $peak"
$report += ""
$report += "--- HPA samples (1s interval) ---"
$report += $samples
$report += ""
$report += "--- k6 summary ---"
$report += ($k6Output | Select-Object -Last 30)

$report | ForEach-Object { Write-Host $_ }
if ($OutFile) {
    $report | Out-File -FilePath $OutFile -Encoding utf8
    Write-Host "`nsaved to $OutFile"
}
