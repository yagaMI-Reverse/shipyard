<#
Shared helpers for the ShipYard scripts.

Windows PowerShell turns *any* stderr output from a native command into a
terminating error when $ErrorActionPreference is 'Stop'. docker, kind and
terraform all write ordinary progress to stderr, so calling them directly makes
a perfectly successful command look like a failure:

    terraform : ╷
    + CategoryInfo : NotSpecified: (...) [], RemoteException

Invoke-Native runs them with stderr merged into stdout and judges success the
way the tools themselves do — by exit code.
#>

function Invoke-Native {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Exe,
        [string[]]$Arguments = @(),
        [switch]$Quiet
    )

    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($Quiet) {
            & $Exe @Arguments 2>&1 | Out-Null
        }
        else {
            # `2>&1` wraps each stderr line in an ErrorRecord. Printing that
            # object directly renders "System.Management.Automation.RemoteException"
            # instead of the line the tool actually wrote, so unwrap it first.
            & $Exe @Arguments 2>&1 | ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) {
                    Write-Host $_.Exception.Message
                }
                else {
                    Write-Host $_
                }
            }
        }
        if ($LASTEXITCODE -ne 0) {
            throw "$Exe $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        $ErrorActionPreference = $previous
    }
}

function Write-Step {
    param([string]$Message)
    Write-Host "`n=== $Message ===" -ForegroundColor Cyan
}
