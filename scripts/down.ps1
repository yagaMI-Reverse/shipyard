<#
.SYNOPSIS
    Destroy the ShipYard environment.

.DESCRIPTION
    `terraform destroy` removes the Helm releases first and the cluster last.
    Destroying the cluster alone would leave state pointing at releases that no
    longer exist, so the ordering matters even for a throwaway environment.
#>
[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$tf = Join-Path (Split-Path -Parent $PSScriptRoot) "terraform"

Push-Location $tf
try {
    if ($Force) {
        terraform destroy -input=false -auto-approve
    }
    else {
        terraform destroy -input=false
    }
}
finally {
    Pop-Location
}
