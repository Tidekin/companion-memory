$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$bankRoot = Join-Path $PSScriptRoot 'bank/suite-v1'
$audioItems = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'audio-to-synthesize.jsonl') -Encoding UTF8 | ForEach-Object { $_ | ConvertFrom-Json }
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = @($speaker.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'zh-*' })
if ($voices.Count -eq 0) { throw 'No installed Chinese voice' }
$speaker.SelectVoice($voices[0].VoiceInfo.Name)
$speaker.Rate = -1
$speaker.Volume = 100
foreach ($item in $audioItems) {
    $target = [IO.Path]::GetFullPath((Join-Path $bankRoot $item.asset))
    $allowed = [IO.Path]::GetFullPath($bankRoot) + [IO.Path]::DirectorySeparatorChar
    if (-not $target.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) { throw 'Asset path outside new bank' }
    if (Test-Path -LiteralPath $target) { throw "Existing audio cannot be overwritten: $($item.source_id)" }
    $speaker.SetOutputToWaveFile($target)
    $speaker.Speak($item.text)
    $speaker.SetOutputToNull()
    Write-Output $item.source_id
}
$speaker.Dispose()
