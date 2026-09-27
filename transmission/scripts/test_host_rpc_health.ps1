$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'host-rpc-health.ps1')

# Windows-loopback only. Each job owns its listener; no production endpoint,
# Docker container, external dependency or system configuration is touched.
function Test-ProbeCase([string]$Case, [int]$ExpectedCode, [int]$Budget = 1000) {
    $job = Start-Job -ArgumentList $Case -ScriptBlock {
        param($Case)
        $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
        $listener.Start()
        Write-Output $listener.LocalEndpoint.Port
        try {
            for ($i = 0; $i -lt 3; $i++) {
                $peer = $listener.AcceptTcpClient()
                try {
                    $stream = $peer.GetStream()
                    $reader = [IO.StreamReader]::new($stream)
                    $first = $reader.ReadLine()
                    if ($first -notmatch '^POST /transmission/rpc HTTP/') { throw 'Unexpected method/path' }
                    $length = 0
                    $token = ''
                    while ($line = $reader.ReadLine()) {
                        if ($line -match '^Content-Length: (\d+)') { $length = [int]$Matches[1] }
                        if ($line -match '^X-Transmission-Session-Id: (.+)') { $token = $Matches[1] }
                    }
                    $chars = [char[]]::new($length)
                    $read = 0
                    while ($read -lt $length) { $read += $reader.Read($chars, $read, $length - $read) }
                    $request = (-join $chars) | ConvertFrom-Json
                    if ($request.method -ne 'session-stats' -or $request.tag -ne 1) { throw 'Unexpected RPC body' }
                    $status = '200 OK'
                    $headers = ''
                    $body = '{"result":"success","tag":1,"arguments":{"activeTorrentCount":1,"torrentCount":2,"downloadSpeed":0,"uploadSpeed":10}}'
                    if (($Case -in @('negotiate', 'budget') -and $i -eq 0) -or ($Case -eq 'renew' -and $i -lt 2) -or $Case -in @('missing-token', 'loop')) {
                        $status = '409 Conflict'; $body = ''
                        if ($Case -ne 'missing-token') { $headers = "X-Transmission-Session-Id: token-$i`r`n" }
                    } elseif ($Case -in @('negotiate', 'renew', 'budget') -and $token -ne "token-$($i-1)") {
                        throw 'Token was not renewed'
                    }
                    if ($Case -eq 'invalid') { $body = '{broken' }
                    if ($Case -eq 'wrong-tag') { $body = $body.Replace('"tag":1', '"tag":2') }
                    if ($Case -eq 'missing-field') { $body = $body.Replace('"uploadSpeed":10', '"other":10') }
                    if ($Case -eq 'http-error') { $status = '401 Unauthorized' }
                    if ($Case -eq 'oversize') { $body = 'x' * 70000 }
                    if ($Case -eq 'budget') { Start-Sleep -Milliseconds 160 }
                    $wire = [Text.Encoding]::UTF8.GetBytes("HTTP/1.1 $status`r`n${headers}Content-Length: $($body.Length)`r`nConnection: close`r`n`r`n")
                    $stream.Write($wire, 0, $wire.Length); $stream.Flush()
                    if ($Case -eq 'slow-body') { Start-Sleep -Milliseconds 800 }
                    if ($Case -eq 'truncated') { $body = $body.Substring(0, 10) }
                    $bytes = [Text.Encoding]::UTF8.GetBytes($body)
                    $stream.Write($bytes, 0, $bytes.Length); $stream.Flush()
                    if ($status -ne '409 Conflict') { break }
                } finally { $peer.Dispose() }
            }
        } finally { $listener.Stop() }
    }
    try {
        $ready = [Diagnostics.Stopwatch]::StartNew()
        $port = $null
        while (-not $port -and $ready.Elapsed.TotalSeconds -lt 10) {
            $port = Receive-Job $job
            if (-not $port) { Start-Sleep -Milliseconds 50 }
        }
        if (-not $port) { throw "Mock did not start: $Case" }
        $result = Invoke-HostTransmissionProbe -Uri "http://127.0.0.1:$port/transmission/rpc" -DeadlineMilliseconds $Budget
        if ($result.FailureCode -ne $ExpectedCode -or $result.Up -ne [int]($ExpectedCode -eq 0)) { throw "${Case}: unexpected result $($result | ConvertTo-Json -Compress)" }
        if ($ExpectedCode -eq 2 -and ($result.DeadlineExceeded -ne 1 -or $result.AttemptSeconds -gt 0.7)) { throw "${Case}: deadline not bounded" }
        $metric = Format-HostTransmissionMetric $result
        if ($ExpectedCode -ne 0 -and $metric -match ',rpc_seconds=') { throw 'Failure fabricated successful latency' }
        if ($metric -match 'token-|exception|Unauthorized') { throw 'Sensitive diagnostic leaked to metric' }
        if ($ExpectedCode -eq 0) {
            [void](Wait-Job $job -Timeout 3)
            if ($job.State -ne 'Completed') { throw "Mock did not complete: $Case" }
            Receive-Job $job -ErrorAction Stop | Out-Null
        }
        Write-Output "PASS $Case"
    } finally {
        Stop-Job $job
        Remove-Job $job -Force
    }
}

Test-ProbeCase 'success' 0
Test-ProbeCase 'negotiate' 0
Test-ProbeCase 'renew' 0
Test-ProbeCase 'missing-token' 5
Test-ProbeCase 'loop' 5
Test-ProbeCase 'invalid' 4
Test-ProbeCase 'wrong-tag' 4
Test-ProbeCase 'missing-field' 4
Test-ProbeCase 'http-error' 3
Test-ProbeCase 'truncated' 1
Test-ProbeCase 'oversize' 1
Test-ProbeCase 'slow-body' 2 200
Test-ProbeCase 'budget' 2 250
$culture = [Threading.Thread]::CurrentThread.CurrentCulture
try {
    [Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::GetCultureInfo('fr-FR')
    $metric = Format-HostTransmissionMetric ([pscustomobject]@{ Up=1; FailureCode=0; DeadlineExceeded=0; Slow=0; AttemptSeconds=0.25; ObservedAt=1 })
    if ($metric -notmatch 'rpc_seconds=0\.25$') { throw 'Metric number is locale dependent' }
} finally { [Threading.Thread]::CurrentThread.CurrentCulture = $culture }
Write-Output 'PASS invariant metric formatting'
