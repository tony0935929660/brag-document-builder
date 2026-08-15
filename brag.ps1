param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is not installed or not available in PATH."
}

if (-not (Test-Path -LiteralPath ".env")) {
    throw "Missing .env. Copy .env.example to .env and fill OPENAI_API_KEY and VAULT_PATH first."
}

$serviceName = "brag-cli"

# Build first so a fresh clone can run commands directly.
docker compose build $serviceName | Out-Host

if (-not $CliArgs -or $CliArgs.Count -eq 0) {
    docker compose run --rm $serviceName --help | Out-Host
    exit $LASTEXITCODE
}

docker compose run --rm -it $serviceName @CliArgs | Out-Host
exit $LASTEXITCODE
