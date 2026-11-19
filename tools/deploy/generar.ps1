param(
    [Parameter(Mandatory=$true)][string]$Salida,
    [Parameter(Mandatory=$true)][string[]]$Archivos
)
$ErrorActionPreference = 'Stop'
$raiz = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$python = Join-Path $raiz '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'No se encuentra el Python del entorno virtual.' }
Push-Location $raiz
try {
    & $python (Join-Path $PSScriptRoot 'paquete.py') --crear $Salida @Archivos
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el paquete.' }
} finally { Pop-Location }
