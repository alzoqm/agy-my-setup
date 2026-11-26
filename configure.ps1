$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $py) {
    Write-Error "Python 3 is required."
    exit 1
}
& $py.Source (Join-Path $PSScriptRoot "configure.py") @args
exit $LASTEXITCODE
