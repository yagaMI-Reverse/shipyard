<#
.SYNOPSIS
    Bring up the whole ShipYard environment from nothing.

.DESCRIPTION
    Builds both images, creates the kind cluster with Terraform, side-loads the
    images into the cluster's nodes, then applies the rest of the stack
    (ingress-nginx, metrics-server, the DocuChat release).

    The cluster is applied first, on its own, because the helm and kubernetes
    providers are configured from its kubeconfig and Terraform evaluates
    provider configuration before it applies anything. One targeted apply, then
    the full one — see the README section "Why two applies".

.EXAMPLE
    ./scripts/up.ps1
    ./scripts/up.ps1 -SkipBuild -Tag v1.2.3
#>
[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [string]$Tag = "dev",
    [string]$ClusterName = "shipyard"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_common.ps1")

$repo = Split-Path -Parent $PSScriptRoot
$tf = Join-Path $repo "terraform"
$apiImage = "shipyard/docuchat-api:$Tag"
$webImage = "shipyard/docuchat-web:$Tag"

# --- 1. images ------------------------------------------------------------- #
if (-not $SkipBuild) {
    Write-Step "Building images ($Tag)"
    Invoke-Native docker @('build', '-t', $apiImage, '--build-arg', "APP_VERSION=$Tag", (Join-Path $repo "app\backend"))
    Invoke-Native docker @('build', '-t', $webImage, '--build-arg', "APP_VERSION=$Tag", (Join-Path $repo "app\frontend"))
}

Push-Location $tf
try {
    Write-Step "Terraform: init"
    Invoke-Native terraform @('init', '-input=false') -Quiet

    # Arguments go in as an array: PowerShell mangles native-command flags that
    # are split across backtick-continued lines, which silently turned
    # -target=module.cluster into two broken arguments.
    $varArgs = @('-var', "api_image=$apiImage", '-var', "web_image=$webImage")

    Write-Step "Terraform: cluster"
    Invoke-Native terraform (@('apply', '-input=false', '-auto-approve', '-target=module.cluster') + $varArgs)

    # --- 2. images into the cluster ---------------------------------------- #
    # The chart runs with imagePullPolicy: Never locally, so the nodes must
    # already have these layers; there is no registry in this environment.
    Write-Step "Loading images into kind"
    Invoke-Native kind @('load', 'docker-image', $apiImage, '--name', $ClusterName)
    Invoke-Native kind @('load', 'docker-image', $webImage, '--name', $ClusterName)

    # --- 3. platform + application ----------------------------------------- #
    Write-Step "Terraform: platform + application"
    Invoke-Native terraform (@('apply', '-input=false', '-auto-approve') + $varArgs)

    Write-Step "Ready"
    Invoke-Native terraform @('output')
}
finally {
    Pop-Location
}
