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

运行发布构建：

```text
py tools/build_pdfs.py
py tools/fill_page_references.py
py tools/build_pdfs.py
```

生成后应使用 Poppler 渲染代表性页面，并检查字体、IPA、表格分页、页码和可提取文本。

工具只能辅助检查，不能替代人工的语言准确性和教学适切性审查。
