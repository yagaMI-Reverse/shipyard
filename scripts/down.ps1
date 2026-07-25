<#
.SYNOPSIS
    Destroy the ShipYard environment.

.DESCRIPTION
    `terraform destroy` removes the Helm releases first and the cluster last.
    Destroying the cluster alone would leave state pointing at releases that no
    longer exist, so the ordering matters even for a throwaway environment.

.EXAMPLE
    ./scripts/down.ps1 -Force
#>
[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

$tf = Join-Path (Split-Path -Parent $PSScriptRoot) "terraform"

Push-Location $tf
try {
    Write-Step "Terraform: destroy"
    # Not $args — that is an automatic variable in PowerShell.
    $tfArgs = @('destroy', '-input=false')
    if ($Force) { $tfArgs += '-auto-approve' }
    Invoke-Native terraform $tfArgs
}
finally {
    Pop-Location
}
