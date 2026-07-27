<#
.SYNOPSIS
    Manual proof server for vuln A (fetch_url has no domain allow-list, no
    untrusted-data wrapping). Run this in its own terminal, then in a second
    terminal call main.fetch_url() directly against the URL this prints.

.EXAMPLE
    ./attacks/manual_vuln_a_server.ps1 -Port 8123
    # then, from the project root, in a second terminal:
    & ".venv\Scripts\python.exe" -c "import main; print(main.fetch_url('http://127.0.0.1:8123/payload.html'))"
#>
param(
    [int]$Port = 8123
)

$payloadPath = Join-Path $PSScriptRoot "fixtures\manual_vuln_a_payload.html"
if (-not (Test-Path $payloadPath)) {
    throw "Payload not found at $payloadPath"
}
$payloadBytes = [System.IO.File]::ReadAllBytes($payloadPath)

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://127.0.0.1:$Port/")
$listener.Start()

Write-Host "Serving $payloadPath"
Write-Host "  -> http://127.0.0.1:$Port/payload.html"
Write-Host "Nothing anywhere in main.py restricts which host/port fetch_url will hit --"
Write-Host "this arbitrary local port is never configured or allow-listed anywhere."
Write-Host "Ctrl+C to stop.`n"

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        $context.Response.ContentType = "text/html"
        $context.Response.OutputStream.Write($payloadBytes, 0, $payloadBytes.Length)
        $context.Response.OutputStream.Close()
        Write-Host "[served] $($context.Request.HttpMethod) $($context.Request.Url)"
    }
} finally {
    $listener.Stop()
    $listener.Close()
}
