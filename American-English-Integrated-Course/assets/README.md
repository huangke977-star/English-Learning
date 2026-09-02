# Assets

本目录存放教材使用的音频、插图、打印资源和其他静态文件。

命名建议：

```text
[册号]-[章节号]-[材料类型]-[序号].[扩展名]
```

示例：`02-05-listening-01.mp3`

每个资源都应在使用它的 Markdown 文件中注明用途；无来源或授权不明的资源不得加入项目。

音频生成使用本机 TTS 工具。生成前应先完成清单中的脚本核对；生成后逐条检查发音、语速、重音和语调，再把 MP3 路径写回对应章节。当前 `audio/complete-course/` 已提供 Book0-Book9 每个单元的自然速度和慢速 MP3，共 220 条核心音频；Book2 另有 9 条重音、弱读、完整/自然形式和语调对比音频。全部音频为 AI 生成的 Microsoft Zira 系统语音；系统 TTS 的重音和弱读仅作辅助，不能替代真人示范。

统一清单见 `complete-audio-manifest.md`，专项审查见 `../09-Reviews-and-Answers/reviews/complete-audio-review.md`。需要重新生成或续跑时，运行 `tools/generate_course_audio.ps1`；脚本默认跳过已存在文件。
