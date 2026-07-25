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

$repo = Split-Path -Parent $PSScriptRoot
$tf = Join-Path $repo "terraform"
$apiImage = "shipyard/docuchat-api:$Tag"
$webImage = "shipyard/docuchat-web:$Tag"

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

# --- 1. images ------------------------------------------------------------- #
if (-not $SkipBuild) {
    Step "Building images ($Tag)"
    docker build -t $apiImage --build-arg "APP_VERSION=$Tag" (Join-Path $repo "app\backend")
    if ($LASTEXITCODE -ne 0) { throw "backend image build failed" }
    docker build -t $webImage --build-arg "APP_VERSION=$Tag" (Join-Path $repo "app\frontend")
    if ($LASTEXITCODE -ne 0) { throw "frontend image build failed" }
}

# --- 2. cluster ------------------------------------------------------------ #
Step "Terraform: cluster"
Push-Location $tf
try {
    terraform init -input=false | Out-Null

    # Arguments are passed as an array: PowerShell mangles native-command flags
    # that are split across backtick-continued lines, which silently turned
    # -target=module.cluster into two broken arguments.
    $varArgs = @('-var', "api_image=$apiImage", '-var', "web_image=$webImage")
    $clusterArgs = @('apply', '-input=false', '-auto-approve', '-target=module.cluster') + $varArgs
    & terraform @clusterArgs
    if ($LASTEXITCODE -ne 0) { throw "cluster apply failed" }

    # --- 3. images into the cluster ---------------------------------------- #
    # The chart runs with imagePullPolicy: Never locally, so the nodes must
    # already have these layers; there is no registry in this environment.
    Step "Loading images into kind"
    kind load docker-image $apiImage --name $ClusterName
    kind load docker-image $webImage --name $ClusterName

    # --- 4. platform + application ----------------------------------------- #
    Step "Terraform: platform + application"
    $fullArgs = @('apply', '-input=false', '-auto-approve') + $varArgs
    & terraform @fullArgs
    if ($LASTEXITCODE -ne 0) { throw "full apply failed" }

    Step "Ready"
    terraform output
}
finally {
    Pop-Location
}
