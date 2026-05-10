$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $projectRoot ".env"
$examplePath = Join-Path $projectRoot ".env.example"

if (-not (Test-Path $envPath)) {
  Copy-Item $examplePath $envPath
  Write-Host "Created .env. Please fill DEVFLOW_LLM_API_KEY first." -ForegroundColor Yellow
  Write-Host $envPath
  exit 1
}

foreach ($rawLine in Get-Content $envPath) {
  $line = $rawLine.Trim()
  if ($line.Length -eq 0) {
    continue
  }
  if ($line.StartsWith("#")) {
    continue
  }

  $parts = $line.Split("=", 2)
  if ($parts.Count -eq 2) {
    $name = $parts[0].Trim()
    $value = $parts[1].Trim()
    [Environment]::SetEnvironmentVariable($name, $value, "Process")
  }
}

if (-not $env:DEVFLOW_LLM_ENABLED) {
  $env:DEVFLOW_LLM_ENABLED = "true"
}

if (-not $env:DEVFLOW_LLM_BASE_URL) {
  $env:DEVFLOW_LLM_BASE_URL = "https://api.lingyaai.cn"
}

if (-not $env:DEVFLOW_LLM_API_KEY -or $env:DEVFLOW_LLM_API_KEY -like "*API Key*") {
  Write-Host "Please fill a real DEVFLOW_LLM_API_KEY in .env first." -ForegroundColor Yellow
  Write-Host $envPath
  exit 1
}

$python = "python"
if (Get-Command py -ErrorAction SilentlyContinue) {
  $python = "py"
}

Write-Host "Installing backend dependencies..." -ForegroundColor Cyan
& $python -m pip install -r (Join-Path $projectRoot "requirements.txt")

$backendCommand = @"
cd '$projectRoot'
`$env:DEVFLOW_LLM_ENABLED='$env:DEVFLOW_LLM_ENABLED'
`$env:DEVFLOW_LLM_BASE_URL='$env:DEVFLOW_LLM_BASE_URL'
`$env:DEVFLOW_LLM_API_KEY='$env:DEVFLOW_LLM_API_KEY'
$python -m uvicorn backend.main:app --reload --port 8001
"@

Write-Host "Starting DevFlow API at http://127.0.0.1:8001" -ForegroundColor Cyan
$backend = Start-Process powershell -PassThru -ArgumentList @(
  "-NoProfile",
  "-ExecutionPolicy",
  "Bypass",
  "-Command",
  $backendCommand
)

Start-Sleep -Seconds 3

$frontendPath = Join-Path $projectRoot "index.html"
Write-Host "Opening frontend..." -ForegroundColor Cyan
Start-Process $frontendPath

Write-Host ""
Write-Host "DevFlow started." -ForegroundColor Green
Write-Host "Backend PID: $($backend.Id)"
Write-Host "Close the new PowerShell window to stop the backend."
