# load-env.ps1
# Usage: . .\load-env.ps1
# The dot-space prefix (. .\) is required to load vars into current session
param([string]$EnvFile = ".env")

if (-not (Test-Path $EnvFile)) {
    Write-Error "No .env file found at $EnvFile"
    return
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    # Skip comments and empty lines
    if ($line -match "^\s*#" -or $line -eq "") { return }
    # Parse KEY=VALUE
    if ($line -match "^([^=]+)=(.*)$") {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim().Trim('"').Trim("'")
        [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
        Write-Host "  Loaded: $key" -ForegroundColor DarkGray
    }
}
Write-Host "Environment loaded from $EnvFile" -ForegroundColor Green
