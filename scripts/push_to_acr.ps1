<#
Put every image of the compose stack into an Azure Container Registry.

  .\scripts\push_to_acr.ps1 -AcrName autonomize
  .\scripts\push_to_acr.ps1 -AcrName autonomize -ImageTag v1

The stack has three images:
  pa-evidence   built here; api, mcp, loader, agent and the eval services all run it
  hapi, ollama  copied inside Azure with `az acr import`; if Docker Hub rate limits Azure,
                pulled here and pushed instead
Needs: az (logged in with `az login`), docker, and push rights on the registry (AcrPush).
#>
param(
    [Parameter(Mandatory)][string]$AcrName,
    [string]$ImageTag
)

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

function Invoke-Native {
    # Run a native command and stop on a non-zero exit code, which $ErrorActionPreference ignores.
    param([Parameter(Mandatory)][string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command $($Arguments -join ' ') failed with exit code $LASTEXITCODE" }
}

# Compose requires these at parse time. They are runtime settings and never enter an image.
foreach ($name in 'NURSE_TOKEN', 'ADMIN_TOKEN', 'MCP_TOKEN') {
    if (-not (Get-Item "Env:$name" -ErrorAction SilentlyContinue)) { Set-Item "Env:$name" 'unused' }
}

$loginServer = (& az acr show --name $AcrName --query loginServer --output tsv).Trim()
if ($LASTEXITCODE -ne 0 -or -not $loginServer) { throw "registry '$AcrName' not found" }
if (-not $ImageTag) { $ImageTag = (& git rev-parse --short HEAD).Trim() }

# Third-party images: the names with a slash, listed from the compose file so the pins stay in one place.
Remove-Item Env:REGISTRY -ErrorAction SilentlyContinue
$images = & docker compose config --images
if ($LASTEXITCODE -ne 0) { throw 'docker compose config failed' }
foreach ($image in ($images | Where-Object { $_ -match '/' } | Sort-Object -Unique)) {
    Write-Host "import docker.io/$image -> $loginServer/$image"
    try {
        Invoke-Native az @('acr', 'import', '--name', $AcrName, '--source', "docker.io/$image", '--image', $image, '--force')
    }
    catch {
        # Azure pulls from Docker Hub on shared addresses and is often rate limited (HTTP 429).
        Write-Warning "import failed, pulling here and pushing instead: $($_.Exception.Message)"
        Invoke-Native az @('acr', 'login', '--name', $AcrName)
        Invoke-Native docker @('pull', $image)
        Invoke-Native docker @('tag', $image, "$loginServer/$image")
        Invoke-Native docker @('push', "$loginServer/$image")
    }
}

# App image: build once, push once.
Invoke-Native az @('acr', 'login', '--name', $AcrName)
$env:REGISTRY = "$loginServer/"
$env:IMAGE_TAG = $ImageTag
Invoke-Native docker @('compose', 'build', 'api')
Invoke-Native docker @('compose', 'push', 'api')
Write-Host "pushed $loginServer/pa-evidence:$ImageTag"
