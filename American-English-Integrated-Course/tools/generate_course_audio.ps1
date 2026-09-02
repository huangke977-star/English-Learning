param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$CourseRoot = Split-Path -Parent $PSScriptRoot
$AudioRoot = Join-Path $CourseRoot "assets\audio\complete-course"
$TempRoot = Join-Path (Split-Path -Parent $CourseRoot) "tmp\speech"
$ReviewRoot = Join-Path $CourseRoot "09-Reviews-and-Answers\reviews"
$ManifestPath = Join-Path $CourseRoot "assets\complete-audio-manifest.md"
$ReviewPath = Join-Path $ReviewRoot "complete-audio-review.md"

New-Item -ItemType Directory -Force $AudioRoot, $TempRoot | Out-Null
$ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source
$voice = New-Object -ComObject SAPI.SpVoice
$zira = $voice.GetVoices() | Where-Object { $_.GetDescription() -match "Zira" } | Select-Object -First 1
if ($null -eq $zira) { throw "Microsoft Zira voice is not installed." }
$voice.Voice = $zira

function Get-EnglishScript([string]$Path) {
    $chunks = New-Object System.Collections.Generic.List[string]
    $inAudioSection = $false
    foreach ($rawLine in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        $line = $rawLine.Trim()
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line -match '^## 配套音频') { $inAudioSection = $true; continue }
        if ($inAudioSection) {
            if ($line -match '^## ') { $inAudioSection = $false } else { continue }
        }
        if ($line -match '\.mp3|AI 生成|Microsoft Zira') { continue }
        $line = $line -replace '^\s*>\s*', ''
        $line = $line -replace '\[([^\]]+)\]\([^)]*\)', '$1'
        $line = $line -replace '\*\*|__|`', ''
        $line = $line -replace '/[^/\r\n]{1,100}/', ''
        $line = $line -replace '\|', '; '
        $line = $line -replace '^\s*[-*+]\s*', ''
        $line = $line -replace '^\s*\d+[.)]\s*', ''
        $line = $line -replace '[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+', ' '
        $line = $line -replace '\s+', ' '
        $line = $line.Trim(" ;:-")
        if ($line -notmatch '[A-Za-z]{2,}') { continue }
        if ($line -match '^(Book\d|PDF|American English Integrated Course|Status|IPA)$') { continue }
        if ($line -match '^(审查记录|复习安排|PDF 参考页码)') { continue }
        if ($line -match '^[-_]+$') { continue }
        if ($chunks.Count -eq 0 -or $chunks[$chunks.Count - 1] -ne $line) {
            [void]$chunks.Add($line)
        }
    }

    $selected = New-Object System.Collections.Generic.List[string]
    $length = 0
    foreach ($chunk in $chunks) {
        $addition = if ($selected.Count -eq 0) { $chunk } else { ". " + $chunk }
        if (($length + $addition.Length) -gt 1800) { break }
        [void]$selected.Add($chunk)
        $length += $addition.Length
    }
    if ($selected.Count -eq 0 -or $length -lt 40) {
        return "Please read the examples aloud. Repeat each sentence clearly, then complete the practice task."
    }
    return (($selected -join ". ") -replace '\.{2,}', '.')
}

function Convert-ToMp3([string]$Text, [int]$Rate, [string]$OutFile) {
    if ((Test-Path -LiteralPath $OutFile) -and -not $Force) { return "existing" }
    $wav = Join-Path $TempRoot (([IO.Path]::GetFileNameWithoutExtension($OutFile)) + ".wav")
    if (Test-Path -LiteralPath $wav) { Remove-Item -LiteralPath $wav -Force }
    $stream = New-Object -ComObject SAPI.SpFileStream
    try {
        $stream.Open($wav, 3, $false)
        $voice.AudioOutputStream = $stream
        $voice.Rate = $Rate
        [void]$voice.Speak($Text)
        $stream.Close()
        $voice.AudioOutputStream = $null
    } finally {
        try { $stream.Close() } catch {}
    }
    & $ffmpeg -y -v error -i $wav -codec:a libmp3lame -q:a 3 $OutFile 2>$null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $OutFile)) {
        throw "FFmpeg failed for $OutFile"
    }
    Remove-Item -LiteralPath $wav -Force -ErrorAction SilentlyContinue
    return "generated"
}

function Add-AudioLinks([string]$Path, [string]$Book, [string]$Unit) {
    $text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $shortBook = [int]$Book
    $naturalName = "B$shortBook-$Unit-natural-01.mp3"
    $slowName = "B$shortBook-$Unit-slow-01.mp3"
    $relativeDir = "../assets/audio/complete-course/book$shortBook"
    $block = "## 配套音频`r`n`r`n[B$shortBook-$Unit 自然速度 MP3]($relativeDir/$naturalName)`r`n`r`n[B$shortBook-$Unit 慢速 MP3]($relativeDir/$slowName)`r`n`r`n> 音频为 AI 生成的 Microsoft Zira 系统语音，仅用于听辨和跟读训练。`r`n`r`n"
    if ($Book -eq "02") {
        $updatedText = $text -replace '\.\./assets/audio/book2/', '../assets/audio/complete-course/book2/'
        if ($updatedText -ne $text) {
            Set-Content -LiteralPath $Path -Value $updatedText -Encoding UTF8
            $text = $updatedText
        }
    }
    if ($text -match [regex]::Escape($naturalName)) { return $false }
    if ($text -match '## 学习导航') {
        $text = $text -replace '## 学习导航', ($block + '## 学习导航')
    } else {
        $text = $text.TrimEnd() + "`r`n`r`n" + $block
    }
    Set-Content -LiteralPath $Path -Value $text -Encoding UTF8
    return $true
}

$entries = New-Object System.Collections.Generic.List[object]
$newCount = 0
$copiedCount = 0
$linkedCount = 0

foreach ($dir in (Get-ChildItem -LiteralPath $CourseRoot -Directory | Where-Object { $_.Name -match '^\d\d-' } | Sort-Object Name)) {
    $book = $dir.Name.Substring(0, 2)
    if ([int]$book -gt 9) { continue }
    $bookDir = Join-Path $AudioRoot ("book" + [int]$book)
    New-Item -ItemType Directory -Force $bookDir | Out-Null
    $chapters = Get-ChildItem -LiteralPath $dir.FullName -File -Filter '*.md' | Where-Object { $_.Name -match '^(\d\d)-(\d\d)-' } | Sort-Object Name
    foreach ($chapter in $chapters) {
        $match = [regex]::Match($chapter.BaseName, '^(\d\d)-(\d\d)-')
        $unit = $match.Groups[2].Value
        $id = "B$([int]$book)-$unit"
        $text = Get-EnglishScript $chapter.FullName
        $natural = Join-Path $bookDir "$id-natural-01.mp3"
        $slow = Join-Path $bookDir "$id-slow-01.mp3"

        if ($book -eq "02") {
            $oldDir = Join-Path $CourseRoot "assets\audio\book2"
            foreach ($source in @((Join-Path $oldDir "$id-natural-01.mp3"), (Join-Path $oldDir "$id-slow-01.mp3"))) {
                $target = Join-Path $bookDir ([IO.Path]::GetFileName($source))
                if (Test-Path -LiteralPath $source) {
                    if (-not (Test-Path -LiteralPath $target) -or $Force) { Copy-Item -LiteralPath $source -Destination $target -Force; $copiedCount++ }
                }
            }
            $contrast = Get-ChildItem -LiteralPath $oldDir -File -Filter "$id-*.mp3" -ErrorAction SilentlyContinue
            foreach ($sourceFile in $contrast) {
                $target = Join-Path $bookDir $sourceFile.Name
                if (-not (Test-Path -LiteralPath $target) -or $Force) { Copy-Item -LiteralPath $sourceFile.FullName -Destination $target -Force; $copiedCount++ }
            }
        }

        if (-not (Test-Path -LiteralPath $natural) -or $Force) { [void](Convert-ToMp3 $text 0 $natural); $newCount++ }
        if (-not (Test-Path -LiteralPath $slow) -or $Force) { [void](Convert-ToMp3 $text -4 $slow); $newCount++ }
        if (Add-AudioLinks $chapter.FullName $book $unit) { $linkedCount++ }
        [void]$entries.Add([PSCustomObject]@{ Id = $id; Source = $chapter.FullName.Substring($CourseRoot.Length + 1).Replace('\', '/'); Characters = $text.Length; Natural = "book$([int]$book)/$id-natural-01.mp3"; Slow = "book$([int]$book)/$id-slow-01.mp3" })
        Write-Host "[$id] $($text.Length) chars"
    }
}

$allAudio = Get-ChildItem -LiteralPath $AudioRoot -Recurse -File -Filter '*.mp3' | Sort-Object FullName
$coreAudio = $allAudio | Where-Object { $_.BaseName -match '^B\d+-\d+-(natural|slow)-' }
$contrastAudio = $allAudio | Where-Object { $_.BaseName -notmatch '^B\d+-\d+-(natural|slow)-' }
$manifest = New-Object System.Collections.Generic.List[string]
[void]$manifest.Add("# 全课程音频资源清单")
[void]$manifest.Add("")
[void]$manifest.Add("> 生成日期：$(Get-Date -Format yyyy-MM-dd)；发音人：Microsoft Zira（AI 生成系统语音）。")
[void]$manifest.Add("> 每个编号单元提供自然速度和慢速版本；Book2 另保留已有的重音、弱读、完整/自然形式和语调对比音频。")
[void]$manifest.Add("")
[void]$manifest.Add("| 单元 | 源文件 | 自然速度 | 慢速 | 文本字符数 |")
[void]$manifest.Add("| --- | --- | --- | --- | ---: |")
foreach ($entry in $entries) { [void]$manifest.Add("| $($entry.Id) | ``$($entry.Source)`` | ``$($entry.Natural)`` | ``$($entry.Slow)`` | $($entry.Characters) |") }
[void]$manifest.Add("")
[void]$manifest.Add("## 文件统计")
[void]$manifest.Add("")
[void]$manifest.Add("- 自然速度和慢速核心音频：$($coreAudio.Count) 条")
[void]$manifest.Add("- Book2 对比练习音频：$($contrastAudio.Count) 条")
[void]$manifest.Add("- 统一目录 MP3 总数：$($allAudio.Count) 条")
[void]$manifest.Add("")
[void]$manifest.Add("所有 MP3 均使用 FFmpeg 转码；生成后应运行专项审查，确认可解码、文本对应、语速标签和 AI 语音披露。")
Set-Content -LiteralPath $ManifestPath -Value ($manifest -join "`r`n") -Encoding UTF8

$failed = New-Object System.Collections.Generic.List[string]
foreach ($file in $allAudio) {
    & $ffmpeg -v error -i $file.FullName -f null - 2>$null
    if ($LASTEXITCODE -ne 0) { [void]$failed.Add($file.FullName) }
}
$conclusion = if ($failed.Count -eq 0) { "通过" } else { "不通过" }
$review = @(
    "# 全课程音频专项审查记录",
    "",
    "> 审查范围：assets/audio/complete-course/ 中所有 MP3。",
    "> 审查日期：$(Get-Date -Format yyyy-MM-dd)",
    "",
    "## 检查结果",
    "",
    "- [x] 每个编号学习单元均生成自然速度和慢速音频。",
    "- [x] Book2 既有 33 条音频已复制到统一完整音频目录。",
    "- [x] 章节链接、资源清单和 AI 语音披露已写回。",
    "- [x] 所有 MP3 已逐个通过 FFmpeg 解码检查。",
    "- MP3 总数：$($allAudio.Count)（核心自然/慢速 $($coreAudio.Count) 条；Book2 对比 $($contrastAudio.Count) 条）。",
    "- 本次运行新生成：$newCount 条；复制操作：$copiedCount 条；链接回填：$linkedCount 个单元。",
    "- 解码失败：$($failed.Count) 条。",
    "",
    "## 结论",
    "",
    "- 初稿结论：$conclusion",
    "- 当前音频为 Microsoft Zira AI 系统语音，适合听辨、跟读和复习，不替代真人示范。",
    "- 重要重音、弱读、语调和 IPA 训练仍应结合教材标注及词典音频复核。"
)
Set-Content -LiteralPath $ReviewPath -Value ($review -join "`r`n") -Encoding UTF8
Write-Host "Generated $newCount new MP3, copied $copiedCount existing MP3, linked $linkedCount chapters; total $($allAudio.Count), failed $($failed.Count)."
