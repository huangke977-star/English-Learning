# Tools

本目录用于存放教材维护脚本，后续可加入：

- Markdown 格式检查
- 必填字段检查
- 重复例句和重复标题检查
- IPA、术语和禁用中文谐音检查
- 索引生成
- PDF 转换前检查

当前提供：

- `build_pdfs.py`：从学习者 Markdown 源文件生成整套教材和 Book0-Book9 分册 PDF，并生成页面索引。
- `fill_page_references.py`：根据整套 PDF 页面索引回填各单元“学习导航”中的 PDF 参考页码。
- `build_mobile_site.py`：从 Markdown 生成手机端 PWA、单元音频面板以及逐词/音素音频清单。
- `generate_inline_audio.ps1`：使用 Microsoft Zira 生成逐词/逐句短音频；标记重音的目标词会单独应用音高、时长和音量对比。
- `generate_pure_phoneme_audio.ps1`：优先调用开源 eSpeak NG 的 `[[...]]` 音素输入生成纯音素 MP3，没有 eSpeak 时回退为 Zira 的近似载体音。

纯音素生成依赖本机安装的 eSpeak NG（Windows 官方发布页：
<https://github.com/espeak-ng/espeak-ng/releases>）。项目不把安装程序或二进制提交进仓库；生成文件仅是学习辅助合成音，需与词典真人音频交叉复核。

运行发布构建：

```text
py tools/build_pdfs.py
py tools/fill_page_references.py
py tools/build_pdfs.py
```

生成后应使用 Poppler 渲染代表性页面，并检查字体、IPA、表格分页、页码和可提取文本。

工具只能辅助检查，不能替代人工的语言准确性和教学适切性审查。
