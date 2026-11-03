param(
    [string]$ReadinessUrl = "https://patchpilot-rurc.onrender.com/api/public/readiness",
    [string]$OutputPath = "launch-proof.json"
)

$started = [DateTimeOffset]::UtcNow
$timer = [System.Diagnostics.Stopwatch]::StartNew()
$statusCode = $null
$body = $null
$errorMessage = $null

try {
    $response = Invoke-WebRequest -Uri $ReadinessUrl -Method Get -TimeoutSec 120 -UseBasicParsing
    $statusCode = [int]$response.StatusCode
    $body = $response.Content | ConvertFrom-Json
}
catch {
    $errorMessage = $_.Exception.Message
    if ($_.Exception.Response) {
        try { $statusCode = [int]$_.Exception.Response.StatusCode } catch { }
    }
}
finally { $timer.Stop() }

$proof = [ordered]@{
    checked_at_utc = $started.ToString("o")
    readiness_url = $ReadinessUrl
    elapsed_ms = [long]$timer.ElapsedMilliseconds
    status_code = $statusCode
    readiness = $body
    error = $errorMessage
    note = "No credentials are sent or recorded. Review before sharing."
}
$absoluteOutput = [System.IO.Path]::GetFullPath($OutputPath)
$json = $proof | ConvertTo-Json -Depth 12
[System.IO.File]::WriteAllText($absoluteOutput, $json, [System.Text.UTF8Encoding]::new($false))
Write-Host "Wrote launch evidence to $absoluteOutput"
if ($statusCode -ne 200 -or -not $body -or -not $body.gates) {
    Write-Error "Launch readiness endpoint did not return a gate report."
    exit 1
}
$stageZeroReady = @("G1", "G2") | ForEach-Object {
    $gateId = $_
    @($body.gates | Where-Object { $_.id -eq $gateId -and $_.status -eq "pass" }).Count -eq 1
} | Where-Object { -not $_ }
if ($stageZeroReady.Count -gt 0) {
    Write-Error "Launch 0 is blocked: G1 deployment and G2 bundled-sample gates must both pass."
    exit 1
}
if (-not $body.public_ai_enabled) {
    Write-Warning "Launch 0 gates passed. Public AI remains off until all remaining gates pass."
    exit 0
}
Write-Host "All launch gates passed; public AI is enabled by the backend gate policy."
