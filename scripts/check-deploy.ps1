param(
    [string]$RenderUrl = "https://patchpilot-rurc.onrender.com",
    [string]$VercelUrl = "https://patchpilot-delta.vercel.app",
    [string]$OutputPath = "deploy-proof.json"
)

$ErrorActionPreference = "Stop"
$results = [System.Collections.Generic.List[object]]::new()

function Invoke-Probe {
    param(
        [string]$Name,
        [string]$Uri,
        [int]$TimeoutSeconds = 120,
        [hashtable]$Headers = @{}
    )

    $started = [DateTimeOffset]::UtcNow
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $statusCode = $null
    $responseHeaders = @{}
    $body = ""
    $errorMessage = $null

    try {
        $response = Invoke-WebRequest -Uri $Uri -Method Get -Headers $Headers `
            -TimeoutSec $TimeoutSeconds -UseBasicParsing
        $statusCode = [int]$response.StatusCode
        foreach ($key in $response.Headers.Keys) {
            $responseHeaders[$key] = [string]$response.Headers[$key]
        }
        $body = [string]$response.Content
    }
    catch {
        $errorMessage = $_.Exception.Message
        if ($_.Exception.Response) {
            try {
                $statusCode = [int]$_.Exception.Response.StatusCode
                foreach ($key in $_.Exception.Response.Headers.AllKeys) {
                    $responseHeaders[$key] = [string]$_.Exception.Response.Headers[$key]
                }
                $stream = $_.Exception.Response.GetResponseStream()
                if ($stream) {
                    $reader = [System.IO.StreamReader]::new($stream)
                    $body = $reader.ReadToEnd()
                    $reader.Dispose()
                }
            }
            catch { }
        }
    }
    finally { $timer.Stop() }

    $result = [ordered]@{
        name = $Name
        url = $Uri
        timestamp_utc = $started.ToString("o")
        elapsed_ms = [long]$timer.ElapsedMilliseconds
        status_code = $statusCode
        headers = $responseHeaders
        body = $body
        error = $errorMessage
    }
    $results.Add([pscustomobject]$result)
    Write-Host ("{0}: HTTP {1}; {2} ms" -f $Name, $(if ($null -eq $statusCode) { "no response" } else { $statusCode }), $timer.ElapsedMilliseconds)
}

Invoke-Probe -Name "render_health" -Uri "$($RenderUrl.TrimEnd('/'))/api/health" -TimeoutSeconds 120
Invoke-Probe -Name "vercel_root" -Uri "$($VercelUrl.TrimEnd('/'))/" -TimeoutSeconds 120
Invoke-Probe -Name "vercel_spa_deep_link" -Uri "$($VercelUrl.TrimEnd('/'))/some/deep/link" -TimeoutSeconds 120
Invoke-Probe -Name "vercel_api_health" -Uri "$($VercelUrl.TrimEnd('/'))/api/health" -TimeoutSeconds 120
Invoke-Probe -Name "render_foreign_origin_cors" -Uri "$($RenderUrl.TrimEnd('/'))/api/health" `
    -TimeoutSeconds 120 -Headers @{ Origin = "https://foreign-origin.example" }

$corsProbe = $results | Where-Object { $_.name -eq "render_foreign_origin_cors" } | Select-Object -First 1
$allowOrigin = $null
if ($corsProbe) { $allowOrigin = $corsProbe.headers["Access-Control-Allow-Origin"] }
$corsReport = [pscustomobject]@{
    name = "foreign_origin_cors_summary"
    timestamp_utc = [DateTimeOffset]::UtcNow.ToString("o")
    foreign_origin = "https://foreign-origin.example"
    allow_origin_header = $allowOrigin
    rejected_as_expected = [string]::IsNullOrWhiteSpace([string]$allowOrigin)
}
$results.Add($corsReport)

$proof = [ordered]@{
    generated_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    note = "HTTP probe evidence only. No credentials are sent or recorded. Review response bodies before sharing."
    probes = $results.ToArray()
}
$absoluteOutput = [System.IO.Path]::GetFullPath($OutputPath)
$json = $proof | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($absoluteOutput, $json, [System.Text.UTF8Encoding]::new($false))
Write-Host "Wrote deployment evidence to $absoluteOutput"
