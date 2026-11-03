param(
    [string]$ProofPath = "submission-proof.json"
)

$ErrorActionPreference = "Stop"

if ($env:LLM_PROVIDER -ne "meta") {
    Write-Error "Submission requires LLM_PROVIDER=meta."
    exit 1
}
if (-not (Test-Path -LiteralPath $ProofPath)) {
    Write-Error "Submission proof is missing: $ProofPath"
    exit 1
}

try {
    $proof = Get-Content -LiteralPath $ProofPath -Raw | ConvertFrom-Json
} catch {
    Write-Error "Submission proof is not valid JSON."
    exit 1
}

if ($proof.meta_live_test.status -ne "LIVE_CONNECTED" -or -not $proof.meta_live_test.recorded_at) {
    Write-Error "Proof must include a dated LIVE_CONNECTED Meta provider test."
    exit 1
}
foreach ($section in @("evaluation_results", "demo_recordings")) {
    if (-not $proof.$section -or @($proof.$section).Count -eq 0) {
        Write-Error "Proof is missing $section."
        exit 1
    }
    foreach ($item in $proof.$section) {
        if ($item.provider -ne "meta_ai") {
            if ($item.provider -eq "gemini") {
                Write-Error "$section contains Gemini output; label it DEVELOPMENT_PROVIDER_GEMINI and do not submit it as Meta evidence."
            } else {
                Write-Error "$section contains output without Meta provider provenance."
            }
            exit 1
        }
    }
}

Write-Output "Submission provider proof passed: Meta live test, evaluations, and demo recordings are recorded."
