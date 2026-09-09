param(
    [string]$ImageName = "miqat-list",
    [string]$ContainerName = "miqat-list",
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"

Write-Host "Building image '$ImageName'..."
docker build -t $ImageName .
if (-not $?) { throw "docker build failed" }

$existing = docker ps -a --filter "name=^/$ContainerName$" --format "{{.Names}}"
if ($existing) {
    Write-Host "Removing existing container '$ContainerName'..."
    docker rm -f $ContainerName | Out-Null
}

$envFileArgs = @()
if (Test-Path .env) {
    $envFileArgs = @("--env-file", ".env")
} else {
    Write-Warning "No .env file found - SECRET_KEY/GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET are required and the app will fail to start. Copy .env.example to .env and fill it in."
}

Write-Host "Starting container '$ContainerName' on http://localhost:$Port ..."
docker run -d --rm --name $ContainerName -p "${Port}:8080" @envFileArgs $ImageName
if (-not $?) { throw "docker run failed" }

Write-Host "Running. Logs: docker logs -f $ContainerName"
Write-Host "Stop with:      docker stop $ContainerName"
