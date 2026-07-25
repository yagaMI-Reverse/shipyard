<#
.SYNOPSIS
    Delete a running pod and measure how long the cluster takes to replace it.

.DESCRIPTION
    Kills one API pod while probing the service through the Ingress, so the
    result covers both halves of self-healing: a replacement pod reaches Ready
    on its own, and traffic kept flowing while it did.

.EXAMPLE
    ./scripts/proof-self-heal.ps1 -OutFile docs/proofs/self-healing.txt
#>
[CmdletBinding()]
param(
    [string]$Url = "http://docuchat.localtest.me:8080/api/healthz",
    [string]$Namespace = "docuchat",
    [string]$Deployment = "shipyard-docuchat-api",
    [int]$IntervalMs = 100,
    [string]$OutFile
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$env:KUBECONFIG = Join-Path $repo "terraform\kubeconfig"

$before = kubectl get pods -n $Namespace -l app.kubernetes.io/component=api -o name
$victim = ($before | Select-Object -First 1)
Write-Host "=== Deleting $victim ===" -ForegroundColor Cyan
Write-Host "pods before: $(($before | Measure-Object).Count)"

$start = Get-Date
kubectl delete $victim -n $Namespace --wait=false | Out-Null

# Poll the Deployment rather than using `kubectl wait --for=condition=Ready
# pod -l ...`: that selector also matches the pod being terminated, so it can
# report success against the very pod we just killed.
$healer = Start-Job -ScriptBlock {
    param($kubeconfig, $ns, $deploy, $victimName)
    $env:KUBECONFIG = $kubeconfig
    $deadline = (Get-Date).AddSeconds(180)
    while ((Get-Date) -lt $deadline) {
        $d = kubectl get deploy $deploy -n $ns -o json | ConvertFrom-Json
        $gone = -not (kubectl get pods -n $ns -o name | Select-String -SimpleMatch $victimName)
        if ($gone -and $d.status.readyReplicas -eq $d.spec.replicas -and $d.status.updatedReplicas -eq $d.spec.replicas) {
            return "replacement ready: $($d.status.readyReplicas)/$($d.spec.replicas) replicas, victim gone"
        }
        Start-Sleep -Milliseconds 500
    }
    return "TIMEOUT waiting for the deployment to recover"
} -ArgumentList $env:KUBECONFIG, $Namespace, $Deployment, ($victim -replace '^pod/', '')

$total = 0; $fail = 0
while ($healer.State -eq "Running") {
    $total++
    try {
        $code = [int](Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5).StatusCode
    }
    catch {
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode } else { $code = 0 }
    }
    if ($code -ne 200) { $fail++ }
    Start-Sleep -Milliseconds $IntervalMs
}
$recovery = (Get-Date) - $start
$waitOutput = Receive-Job $healer
Remove-Job $healer

$after = kubectl get pods -n $Namespace -l app.kubernetes.io/component=api -o wide

$report = @()
$report += "=== Self-healing proof ==="
$report += "deleted pod    : $victim"
$report += "recovery time  : $([math]::Round($recovery.TotalSeconds,1))s to Deployment Available + all pods Ready"
$report += "probes during  : $total"
$report += "failed probes  : $fail"
$report += ""
$report += "--- kubectl wait ---"
$report += $waitOutput
$report += ""
$report += "--- pods after ---"
$report += $after

$report | ForEach-Object { Write-Host $_ }
if ($OutFile) {
    $report | Out-File -FilePath $OutFile -Encoding utf8
    Write-Host "`nsaved to $OutFile"
}
