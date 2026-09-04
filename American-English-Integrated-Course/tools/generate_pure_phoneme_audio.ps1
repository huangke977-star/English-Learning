param(
    [switch]$Force
)

$ErrorActionPreference = "Continue"
$CourseRoot = Split-Path -Parent $PSScriptRoot
$ManifestPath = Join-Path $CourseRoot "assets\pure-phoneme-manifest.json"
$AudioRoot = Join-Path $CourseRoot "assets\audio\phoneme"
$TempRoot = Join-Path $CourseRoot "tmp\pure-phoneme"
$ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source
$ffprobe = (Get-Command ffprobe -ErrorAction Stop).Source

if (-not (Test-Path -LiteralPath $ManifestPath)) {
    throw "Missing $ManifestPath. Run py tools/build_mobile_site.py first."
}

New-Item -ItemType Directory -Force $AudioRoot, $TempRoot | Out-Null
$espeak = $null
$espeakCandidates = @(
    (Get-Command espeak-ng -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    "C:\Program Files\eSpeak NG\espeak-ng.exe",
    "C:\Program Files (x86)\eSpeak NG\espeak-ng.exe"
)
foreach ($candidate in $espeakCandidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) { $espeak = $candidate; break }
}

# eSpeak NG consumes the actual phoneme code and is therefore the canonical
# path.  Keep Microsoft Zira as a local fallback for machines without eSpeak.
$voice = $null
if (-not $espeak) {
    try {
        $voice = New-Object -ComObject SAPI.SpVoice
        $zira = $voice.GetVoices() | Where-Object { $_.GetDescription() -match "Zira" } | Select-Object -First 1
        if ($null -eq $zira) { throw "Microsoft Zira voice is not installed." }
        $voice.Voice = $zira
        $voice.Rate = -2
        $voice.Volume = 100
    } catch {
        throw "eSpeak NG was not found and Microsoft Zira fallback is unavailable: $($_.Exception.Message)"
    }
}
$manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$items = @($manifest.items)
$generated = 0
$existing = 0
$failed = New-Object System.Collections.Generic.List[string]

function Write-SapiWav([string]$Text, [string]$Wav) {
    $stream = New-Object -ComObject SAPI.SpFileStream
    try {
        $stream.Open($Wav, 3, $false)
        $voice.AudioOutputStream = $stream
        [void]$voice.Speak($Text)
    } finally {
        try { $stream.Close() } catch {}
        $voice.AudioOutputStream = $null
    }
}

function Write-EspeakWav([string]$Code, [string]$Wav) {
    if (-not $Code) { throw "Missing eSpeak phoneme code" }
    & $espeak -v en-us -s 120 -p 50 -a 100 -w $Wav "[[$Code]]" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Wav)) {
        throw "eSpeak NG could not synthesize phoneme [$Code]"
    }
}

function Get-TrimBounds([string]$Wav) {
    $duration = [double](& $ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 $Wav)
    $report = (& $ffmpeg -hide_banner -i $Wav -af "silencedetect=noise=-45dB:d=0.05" -f null - 2>&1 | Out-String)
    $events = [regex]::Matches($report, 'silence_(start|end):\s*([0-9.]+)')
    $activeStart = $null
    $leadingEnd = $null
    $trailingStart = $null
    foreach ($event in $events) {
        $kind = $event.Groups[1].Value
        $point = [double]$event.Groups[2].Value
        if ($kind -eq "start") { $activeStart = $point; continue }
        if ($null -eq $activeStart) { continue }
        if ($activeStart -le 0.02 -and $null -eq $leadingEnd) { $leadingEnd = $point }
        if ([math]::Abs($point - $duration) -le 0.08) { $trailingStart = $activeStart }
        $activeStart = $null
    }
    if ($null -ne $activeStart) { $trailingStart = $activeStart }
    $start = if ($null -ne $leadingEnd) { $leadingEnd } else { 0.0 }
    $end = if ($null -ne $trailingStart) { $trailingStart } else { $duration }
    $start = [math]::Max(0.0, $start - 0.02)
    $end = [math]::Min($duration, $end + 0.02)
    if ($end -le $start + 0.05) { $start = 0.0; $end = $duration }
    return @{ Start = $start; Duration = $end - $start }
}

foreach ($item in $items) {
    $output = Join-Path $CourseRoot $item.file.Replace('/', '\')
    if ((Test-Path -LiteralPath $output) -and -not $Force) { $existing++; continue }
    $wav = Join-Path $TempRoot ("$($item.id).wav")
    $stream = $null
    try {
        if ($espeak) {
            Write-EspeakWav ([string]$item.phoneme_code) $wav
        } else {
            Write-SapiWav ([string]$item.text) $wav
        }
        $bounds = Get-TrimBounds $wav
        & $ffmpeg -y -v error -ss $bounds.Start -t $bounds.Duration -i $wav -codec:a libmp3lame -q:a 4 $output 2>$null
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $output)) { throw "FFmpeg could not encode $($item.id)" }
        $generated++
    } catch {
        [void]$failed.Add("$($item.id): $($_.Exception.Message)")
    } finally {
        if ($stream) { try { $stream.Close() } catch {} }
        if ($voice) { $voice.AudioOutputStream = $null }
        Remove-Item -LiteralPath $wav -Force -ErrorAction SilentlyContinue
    }
}

$invalid = New-Object System.Collections.Generic.List[string]
foreach ($item in $items) {
    $output = Join-Path $CourseRoot $item.file.Replace('/', '\')
    if (-not (Test-Path -LiteralPath $output)) { [void]$invalid.Add("missing: $($item.id)"); continue }
    & $ffmpeg -v error -i $output -f null - 2>$null
    if ($LASTEXITCODE -ne 0) { [void]$invalid.Add("decode: $($item.id)") }
}

Write-Host "Pure phoneme audio: generated $generated, existing $existing, failed $($failed.Count), invalid $($invalid.Count)."
if ($failed.Count -or $invalid.Count) {
    ($failed + $invalid) | ForEach-Object { Write-Error $_ }
    exit 1
}
