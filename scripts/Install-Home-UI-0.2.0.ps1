[CmdletBinding()]
param([string]$RouterAddress, [switch]$ValidateOnly)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$expectedManifest = '__BUNDLE_SHA256__'
$manifest = Join-Path $PSScriptRoot 'SHA256SUMS'
if ((Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedManifest) {
    throw 'Update manifest SHA256 mismatch.'
}
$packages = @()
foreach ($line in [System.IO.File]::ReadAllLines($manifest)) {
    if ($line -notmatch '^([a-f0-9]{64})  ([a-zA-Z0-9._+-]+\.apk)$') { throw 'Invalid update manifest.' }
    $expectedPackage = $Matches[1]
    $path = Join-Path $PSScriptRoot $Matches[2]
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedPackage) {
        throw "Package SHA256 mismatch: $path"
    }
    $packages += $path
}
if ($packages.Count -ne 6) { throw 'Expected six update packages.' }
$remoteInstaller = Join-Path $PSScriptRoot 'install_ui_update.sh'
if (-not (Test-Path -LiteralPath $remoteInstaller -PathType Leaf)) { throw 'Remote installer is missing.' }
if ((Get-FileHash -LiteralPath $remoteInstaller -Algorithm SHA256).Hash.ToLowerInvariant() -ne '__INSTALLER_SHA256__') {
    throw 'Remote installer SHA256 mismatch.'
}
if ($ValidateOnly) { Write-Host 'LOCAL VALIDATION PASSED. No router was accessed.'; return }
foreach ($tool in @('ssh.exe','scp.exe')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Windows OpenSSH Client required: $tool" }
}
if ([string]::IsNullOrWhiteSpace($RouterAddress)) { $RouterAddress = Read-Host 'OpenWrt LAN IPv4 address' }
$routerIp = $null
if (-not [System.Net.IPAddress]::TryParse($RouterAddress,[ref]$routerIp) -or
    $routerIp.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { throw 'Enter the router IPv4 address.' }
if ([System.Net.IPAddress]::IsLoopback($routerIp)) { throw 'Use the router LAN address, not this computer.' }
$target = 'root@' + $routerIp.ToString()
$remoteDir = '/tmp/home-ui-0.2.0-' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmss')
$knownHosts = (Join-Path $PSScriptRoot 'ssh-known-hosts').Replace('\','/')
$sshOptions = @('-o',('UserKnownHostsFile=' + $knownHosts))
Write-Host 'Enter the ROUTER root password when prompted. Check its SSH fingerprint on first connection.'
& ssh.exe @sshOptions $target ('mkdir -m 700 ' + $remoteDir)
if ($LASTEXITCODE -ne 0) { throw 'Could not create router staging directory.' }
$upload = @($manifest,$remoteInstaller) + $packages
& scp.exe -O @sshOptions @upload ($target + ':' + $remoteDir + '/')
if ($LASTEXITCODE -ne 0) { throw 'Upload failed. No install was attempted.' }
& ssh.exe @sshOptions $target ('sh ' + $remoteDir + '/install_ui_update.sh ' + $expectedManifest)
if ($LASTEXITCODE -ne 0) { throw "Router installation failed (exit $LASTEXITCODE). Keep this output for diagnosis." }
Write-Host 'INSTALLATION COMPLETE. Refresh the OpenWrt webpage. The router was not rebooted.'
