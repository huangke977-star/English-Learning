# Indexes

本目录维护教材的检索入口。四类内容索引由
`tools/build_content_indexes.py` 生成，源文件变化后可在项目根目录运行：

```powershell
py tools/build_content_indexes.py
```

- `vocabulary-index.md`：Book4 词汇、搭配和短语动词；按词语字母顺序定位。
- `grammar-index.md`：Book3 推荐语法主题；“常见易错表达”单独列在文末，左栏不是范例。
- `speaking-index.md`：Book5 交际功能与推荐句型；易错表达单独列出。
- `ipa-index.md`：Book1 的 IPA 音素及首次重点章节；具体舌位、变体和例词以正文为准。
- `08-scenario-index.md`：Book8 场景索引。
- `09-test-index.md`：Book9 复习与测试索引。
- `page-index.md`：完整 PDF 页面索引；分册索引见 `../output/pdf/bookN-page-index.md`。

新增、删除或重命名教材内容后，应同步更新相关索引。页面索引由
`tools/build_pdfs.py` 自动生成；PDF 排版或源文件发生变化后，必须重新生成 PDF、渲染抽查并更新索引。
