param([uri]$Uri = 'http://127.0.0.1:9091/transmission/rpc')

# Native Windows timing: no Docker CLI or guest clock is involved. Dot-source
# for the disposable HTTP tests; normal execution emits one Influx sample.
function Invoke-HostTransmissionProbe {
    param([uri]$Uri, [ValidateRange(100, 3000)][int]$DeadlineMilliseconds = 3000)
    if (-not $Uri.IsLoopback -or $Uri.Scheme -ne 'http') { throw 'Only loopback HTTP is permitted' }
    Add-Type -AssemblyName System.Net.Http
    $handler = [Net.Http.HttpClientHandler]::new()
    $handler.UseProxy = $false
    $handler.AllowAutoRedirect = $false
    $client = [Net.Http.HttpClient]::new($handler)
    $client.MaxResponseContentBufferSize = 65536
    $cancel = [Threading.CancellationTokenSource]::new()
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $cancel.CancelAfter($DeadlineMilliseconds)
    $up = 0
    $failure = 1 # transport; 2 deadline, 3 HTTP, 4 invalid body, 5 token negotiation
    $token = ''
    try {
        for ($attempt = 0; $attempt -lt 3; $attempt++) {
            $request = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Post, $Uri)
            $request.Headers.ExpectContinue = $false
            $request.Content = [Net.Http.StringContent]::new('{"method":"session-stats","arguments":{},"tag":1}', [Text.Encoding]::UTF8, 'application/json')
            $response = $null
            try {
                if ($token) { [void]$request.Headers.TryAddWithoutValidation('X-Transmission-Session-Id', $token) }
                # ResponseContentRead includes the complete bounded body in the
                # cancellation budget, even if the server sends headers early.
                $failure = 1
                $response = $client.SendAsync($request, [Net.Http.HttpCompletionOption]::ResponseContentRead, $cancel.Token).GetAwaiter().GetResult()
                if ([int]$response.StatusCode -eq 409) {
                    $failure = 5
                    if (-not $response.Headers.Contains('X-Transmission-Session-Id')) { break }
                    $token = @($response.Headers.GetValues('X-Transmission-Session-Id'))[0]
                    if ([string]::IsNullOrWhiteSpace($token)) { break }
                    continue
                }
                $failure = 3
                if ([int]$response.StatusCode -ne 200) { break }
                $failure = 4
                $text = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
                # ConvertFrom-Json can unwrap a one-element root array.
                if (-not $text.TrimStart().StartsWith('{')) { break }
                $body = $text | ConvertFrom-Json -ErrorAction Stop
                if ($body.result -cne 'success' -or $body.tag -isnot [int] -or $body.tag -ne 1 -or $body.arguments -isnot [pscustomobject]) { break }
                $valid = $true
                foreach ($field in @('activeTorrentCount', 'torrentCount', 'downloadSpeed', 'uploadSpeed')) {
                    $value = $body.arguments.$field
                    if (($value -isnot [int] -and $value -isnot [long] -and $value -isnot [double]) -or
                        [double]::IsNaN([double]$value) -or [double]::IsInfinity([double]$value) -or $value -lt 0) { $valid = $false }
                }
                if ($valid) { $up = 1; $failure = 0 }
                break
            } finally {
                if ($response) { $response.Dispose() }
                $request.Dispose()
            }
        }
    } catch {
        # Never send response bodies, credentials, tokens or exception text to telemetry.
        $up = 0
    } finally {
        $watch.Stop()
        if ($cancel.IsCancellationRequested -or $watch.Elapsed.TotalMilliseconds -ge $DeadlineMilliseconds) { $up = 0; $failure = 2 }
        $cancel.Dispose()
        $client.Dispose()
    }
    [pscustomobject]@{
        Up = $up
        FailureCode = $failure
        DeadlineExceeded = [int]($failure -eq 2)
        Slow = [int]($up -eq 1 -and $watch.Elapsed.TotalSeconds -gt 1)
        AttemptSeconds = $watch.Elapsed.TotalSeconds
        ObservedAt = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    }
}

function Format-HostTransmissionMetric($Result) {
    $elapsed = $Result.AttemptSeconds.ToString('R', [Globalization.CultureInfo]::InvariantCulture)
    $fields = "rpc_up=$($Result.Up)i,failure_code=$($Result.FailureCode)i,deadline_exceeded=$($Result.DeadlineExceeded)i,slow=$($Result.Slow)i,attempt_seconds=$elapsed,observed_at=$($Result.ObservedAt)i"
    if ($Result.Up -eq 1) { $fields += ",rpc_seconds=$elapsed" }
    "transmission_host_rpc,service=transmission $fields"
}

if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    $mutex = [Threading.Mutex]::new($false, 'Global\TransmissionHostRpcProbe')
    $locked = $false
    try {
        try { $locked = $mutex.WaitOne(0) }
        catch [Threading.AbandonedMutexException] { $locked = $true }
        if ($locked) { Format-HostTransmissionMetric (Invoke-HostTransmissionProbe -Uri $Uri) }
    } finally {
        if ($locked) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}
