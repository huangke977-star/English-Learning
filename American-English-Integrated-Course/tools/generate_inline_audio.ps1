param(
    [switch]$Force,
    [int]$Limit = 0
)

# FFmpeg emits harmless layout notices on stderr. Validate each exit code below
# instead of turning those notices into terminating PowerShell errors.
$ErrorActionPreference = "Continue"
$CourseRoot = Split-Path -Parent $PSScriptRoot
$ManifestPath = Join-Path $CourseRoot "assets\inline-audio-manifest.json"
$AudioRoot = Join-Path $CourseRoot "assets\audio\inline"
$TempRoot = Join-Path $CourseRoot "tmp\inline-audio"
$ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source
$ffprobe = (Get-Command ffprobe -ErrorAction Stop).Source

if (-not (Test-Path -LiteralPath $ManifestPath)) {
    throw "Missing $ManifestPath. Run py tools/build_mobile_site.py first."
}

New-Item -ItemType Directory -Force $AudioRoot, $TempRoot | Out-Null
$voice = New-Object -ComObject SAPI.SpVoice
$zira = $voice.GetVoices() | Where-Object { $_.GetDescription() -match "Zira" } | Select-Object -First 1
if ($null -eq $zira) {
    throw "Microsoft Zira voice is not installed."
}
$voice.Voice = $zira
$voice.Rate = 0
$voice.Volume = 100
$manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$items = @($manifest.items)
if ($Limit -gt 0) { $items = @($items | Select-Object -First $Limit) }
$generated = 0
$existing = 0
$failed = New-Object System.Collections.Generic.List[string]

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
        if ($kind -eq "start") {
            $activeStart = $point
            continue
        }
        if ($null -eq $activeStart) { continue }
        if ($activeStart -le 0.02 -and $null -eq $leadingEnd) { $leadingEnd = $point }
        if ([math]::Abs($point - $duration) -le 0.08) { $trailingStart = $activeStart }
        $activeStart = $null
    }
    # Some FFmpeg builds do not emit silence_end when EOF occurs in silence.
    if ($null -ne $activeStart) { $trailingStart = $activeStart }
    $start = if ($null -ne $leadingEnd) { $leadingEnd } else { 0.0 }
    $end = if ($null -ne $trailingStart) { $trailingStart } else { $duration }
    $start = [math]::Max(0.0, $start - 0.02)
    $end = [math]::Min($duration, $end + 0.02)
    if ($end -le $start + 0.08) { $start = 0.0; $end = $duration }
    return @{ Start = $start; Duration = $end - $start }
}

function Get-StressMatches([string]$Text) {
    # The teaching files mark sentence focus with capitals (BLUE, I CAN go)
    # and lexical stress with mixed-case spellings (REcord, reCORD). SAPI
    # ignores case, so these words must be rendered as separate segments.
    $ignored = @('I', 'ID', 'HJ', 'IPA', 'SVO', 'SVC', 'SVOO', 'SVOC', 'SVA', 'SV')
    $stressMatches = New-Object System.Collections.Generic.List[object]
    foreach ($match in [regex]::Matches($Text, "[A-Za-z]+(?:['-][A-Za-z]+)*")) {
        $word = $match.Value
        if ($ignored -contains $word -or $word.Length -lt 2) { continue }
        $hasUpper = $word -cmatch '[A-Z]'
        $hasLower = $word -cmatch '[a-z]'
        $upperCount = ([regex]::Matches($word, '[A-Z]')).Count
        # Mixed-case stress or a fully-capitalized content/function word.
        if (($hasUpper -and $hasLower -and $upperCount -ge 2) -or
            ($hasUpper -and -not $hasLower -and $word.Length -ge 2)) {
            [void]$stressMatches.Add($match)
        }
    }
    return $stressMatches.ToArray()
}

function Get-ContextSpeech([string]$Text) {
    # SAPI ignores capitalization in isolated lexical-stress examples. Give
    # heteronyms a grammatical cue so the voice selects the intended stress.
    switch -CaseSensitive ($Text) {
        'REcord' { return 'a record' }
        'reCORD' { return 'to record' }
        'PREsent' { return 'a present' }
        'preSENT' { return 'to present' }
        'PERmit' { return 'a permit' }
        'perMIT' { return 'to permit' }
        default { return '' }
    }
}

function Write-SapiWav([string]$Text, [int]$Rate, [int]$Volume, [string]$Wav) {
    $stream = New-Object -ComObject SAPI.SpFileStream
    try {
        $stream.Open($Wav, 3, $false)
        $voice.AudioOutputStream = $stream
        $voice.Rate = $Rate
        $voice.Volume = $Volume
        [void]$voice.Speak($Text)
    } finally {
        try { $stream.Close() } catch {}
        $voice.AudioOutputStream = $null
        $voice.Rate = 0
        $voice.Volume = 100
    }
}

function Convert-StressedToMp3([string]$Text, [string]$Output, [string]$ItemId) {
    $stress = @(Get-StressMatches $Text)
    if ($stress.Count -eq 0) { return $false }
    $segmentRoot = Join-Path $TempRoot ("stress-" + $ItemId)
    New-Item -ItemType Directory -Force $segmentRoot | Out-Null
    $segments = New-Object System.Collections.Generic.List[string]
    $cursor = 0
    $index = 0
    try {
        foreach ($match in $stress) {
            $prefix = $Text.Substring($cursor, $match.Index - $cursor).Trim()
            if ($prefix) {
                $wav = Join-Path $segmentRoot ("$index-prefix.wav")
                Write-SapiWav $prefix 0 100 $wav
                $segments.Add($wav)
                $index++
            }
            $target = $match.Value.ToLowerInvariant()
            # A slower, louder isolated target is an intentional teaching
            # contrast; no spoken labels are inserted into the learner audio.
            $wav = Join-Path $segmentRoot ("$index-target.wav")
            Write-SapiWav $target -3 100 $wav
            $amplified = Join-Path $segmentRoot ("$index-target-amplified.wav")
            & $ffmpeg -y -v error -i $wav -af 'volume=1.35' $amplified 2>$null
            if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $amplified)) {
                Move-Item -LiteralPath $amplified -Destination $wav -Force
            }
            $segments.Add($wav)
            $index++
            $cursor = $match.Index + $match.Length
        }
        $suffix = $Text.Substring($cursor).Trim()
        if ($suffix) {
            $wav = Join-Path $segmentRoot ("$index-suffix.wav")
            Write-SapiWav $suffix 0 100 $wav
            $segments.Add($wav)
        }
        if ($segments.Count -eq 0) { return $false }
        $inputArgs = @()
        $labels = New-Object System.Collections.Generic.List[string]
        for ($i = 0; $i -lt $segments.Count; $i++) {
            $inputArgs += @('-i', $segments[$i])
            [void]$labels.Add("[$i`:a]")
        }
        $filter = (($labels -join '') + "concat=n=$($segments.Count):v=0:a=1[out]")
        & $ffmpeg -y -v error @inputArgs -filter_complex $filter -map '[out]' -codec:a libmp3lame -q:a 4 $Output 2>$null
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $Output)) {
            throw "FFmpeg could not join stressed segments for $ItemId"
        }
        return $true
    } finally {
        Remove-Item -LiteralPath $segmentRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

foreach ($item in $items) {
    $output = Join-Path $CourseRoot $item.file.Replace('/', '\')
    $hasStress = @(Get-StressMatches ([string]$item.text)).Count -gt 0
    $contextSpeech = Get-ContextSpeech ([string]$item.text)
    if ((Test-Path -LiteralPath $output) -and -not $Force -and -not $hasStress) {
        $existing++
        continue
    }
    $wav = Join-Path $TempRoot ("$($item.id).wav")
    $stream = New-Object -ComObject SAPI.SpFileStream
    try {
        if ($contextSpeech) {
            Write-SapiWav $contextSpeech 0 100 $wav
            $bounds = Get-TrimBounds $wav
            & $ffmpeg -y -v error -ss $bounds.Start -t $bounds.Duration -i $wav -codec:a libmp3lame -q:a 4 $output 2>$null
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $output)) {
                throw "FFmpeg could not encode $($item.id)"
            }
        } elseif (-not (Convert-StressedToMp3 ([string]$item.text) $output ([string]$item.id))) {
            Write-SapiWav ([string]$item.text) 0 100 $wav
            $bounds = Get-TrimBounds $wav
            & $ffmpeg -y -v error -ss $bounds.Start -t $bounds.Duration -i $wav -codec:a libmp3lame -q:a 4 $output 2>$null
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $output)) {
                throw "FFmpeg could not encode $($item.id)"
            }
        }
        $generated++
    } catch {
        [void]$failed.Add("$($item.id): $($_.Exception.Message)")
    } finally {
        try { $stream.Close() } catch {}
        $voice.AudioOutputStream = $null
        Remove-Item -LiteralPath $wav -Force -ErrorAction SilentlyContinue
    }
}

$invalid = New-Object System.Collections.Generic.List[string]
foreach ($item in $items) {
    $output = Join-Path $CourseRoot $item.file.Replace('/', '\')
    if (-not (Test-Path -LiteralPath $output)) {
        [void]$invalid.Add("missing: $($item.id)")
        continue
    }
    & $ffmpeg -v error -i $output -f null - 2>$null
    if ($LASTEXITCODE -ne 0) { [void]$invalid.Add("decode: $($item.id)") }
}

Write-Host "Inline audio: generated $generated, existing $existing, failed $($failed.Count), invalid $($invalid.Count)."
if ($failed.Count -or $invalid.Count) {
    ($failed + $invalid) | ForEach-Object { Write-Error $_ }
    exit 1
}
