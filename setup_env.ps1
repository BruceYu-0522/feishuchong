param(
    [string]$ApiKey = "",
    [string]$BaseUrl = "https://api.lingyaai.cn"
)

$ErrorActionPreference = "Stop"

if (-not $ApiKey.Trim()) {
    $ApiKey = Read-Host "Enter review API Key"
}

if (-not $ApiKey.Trim()) {
    Write-Error "API Key cannot be empty."
}

$envFile = Join-Path $PSScriptRoot ".env"
$content = @(
    "DEVFLOW_LLM_ENABLED=true"
    "DEVFLOW_LLM_BASE_URL=$BaseUrl"
    "DEVFLOW_LLM_API_KEY=$ApiKey"
)

Set-Content -Path $envFile -Value $content -Encoding UTF8
Write-Host ".env generated: $envFile"
Write-Host "Next: docker compose up -d --build"
