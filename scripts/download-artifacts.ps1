param(
    [Parameter(Mandatory = $true)][long]$RunId,
    [string]$Repository = 'joysky77/openwrt-j4125',
    [string]$OutputRoot = (Join-Path $PSScriptRoot '..\artifacts'),
    [string]$TemporaryRoot = 'D:\AiTemp\openwrt-cloud-tools\download-temp',
    [switch]$VerifyOnly,
    [string]$ExistingDirectory
)
$ErrorActionPreference = 'Stop'
if ($RunId -le 0 -or $Repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') {
    throw 'Invalid run ID or repository.'
}
$runJson = gh run view $RunId --repo $Repository --json status,conclusion,headSha,url
if ($LASTEXITCODE -ne 0) { throw 'Cannot read workflow run.' }
$run = $runJson | ConvertFrom-Json
if ($run.status -ne 'completed' -or $run.conclusion -ne 'success') {
    throw "Build is not successful yet: $($run.status)/$($run.conclusion)"
}
if ($VerifyOnly) {
    if (-not $ExistingDirectory -or -not (Test-Path -LiteralPath $ExistingDirectory -PathType Container)) {
        throw 'VerifyOnly requires an existing artifact directory.'
    }
    $destination = [IO.Path]::GetFullPath($ExistingDirectory)
} else {
$destination = [IO.Path]::GetFullPath((Join-Path $OutputRoot ("run-{0}-{1}" -f $RunId, (Get-Date -Format 'yyyyMMdd-HHmmss'))))
if (Test-Path -LiteralPath $destination) { throw 'Destination already exists; preserve old artifacts.' }
New-Item -ItemType Directory -Path $destination -Force | Out-Null
New-Item -ItemType Directory -Path $TemporaryRoot -Force | Out-Null
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
try {
    $env:TEMP = [IO.Path]::GetFullPath($TemporaryRoot)
    $env:TMP = $env:TEMP
    gh run download $RunId --repo $Repository --dir $destination
    if ($LASTEXITCODE -ne 0) { throw 'Artifact download failed.' }
} finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
}
}
# Windows globbing is case-insensitive. Upstream metadata/sha256sums describes
# original filenames, whereas our uppercase SHA256SUMS covers renamed files.
$sums = @(Get-ChildItem -LiteralPath $destination -Recurse -File -Filter SHA256SUMS | Where-Object { $_.Name -ceq 'SHA256SUMS' })
if ($sums.Count -lt 2) { throw 'Expected checksums for firmware and expansion kit.' }
foreach ($sum in $sums) {
    $basePath = [IO.Path]::GetFullPath($sum.DirectoryName) + [IO.Path]::DirectorySeparatorChar
    foreach ($line in Get-Content -LiteralPath $sum.FullName -Encoding UTF8) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { throw "Invalid checksum entry in $($sum.FullName)" }
        $expected = $Matches[1]
        $file = [IO.Path]::GetFullPath((Join-Path $basePath $Matches[2]))
        if (-not $file.StartsWith($basePath, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe checksum path.' }
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing file: $file" }
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
            throw "Checksum mismatch: $file"
        }
    }
}
$run | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $destination 'workflow-run.json') -Encoding utf8
Write-Output "Downloaded and verified: $destination"
Write-Output 'Candidate build only; hardware and stability validation remain pending.'
