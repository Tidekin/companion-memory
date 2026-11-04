param([switch]$Docs)
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    python -X utf8 -B scripts/verify_release.py
    if ($LASTEXITCODE -ne 0) { throw 'Public bundle verification failed' }
    if (-not $Docs) {
        python -m ruff check .
        if ($LASTEXITCODE -ne 0) { throw 'Ruff failed' }
        python -X utf8 -B -m pytest --basetemp=.local/test-temp
        if ($LASTEXITCODE -ne 0) { throw 'Reference tests failed' }
        python -X utf8 -B examples/sqlite_demo.py
        if ($LASTEXITCODE -ne 0) { throw 'SQLite example failed' }
    }
} finally {
    Pop-Location
}
