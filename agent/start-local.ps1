$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
if (-not $env:DEEPSEEK_API_KEY) {
    $secret = Read-Host 'DeepSeek API key (hidden; used only in this terminal session)' -AsSecureString
    $env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
    $secret.Dispose()
}
uv run --no-project python chat_agent.py --provider deepseek
