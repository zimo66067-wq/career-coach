# WF-01 · 材料接收与解析（占位，DuMate 实现）

- **输入**：上传的 PDF/DOCX/TXT 或粘贴文本（须先获用户同意，状态 CONSENT→RESUME_READY）
- **输出**：纯文本 + `pii_removed:true` 标记
- **主路径**：`tools/extract_text.py --input <file> --output out.txt` → `tools/deidentify.py --input out.txt --output clean.txt`
- **备用A**：解析失败（如扫描件 PDF）→ 提示用户「请另存为 txt 后重试」并允许直接粘贴
- **备用B**：去标识化服务异常 → 阻断后续流程并提示，不得将未脱敏文本送入模型
- **退出标准**：输出非空、脱敏扫描（手机号/邮箱/身份证正则）无命中
- **禁止**：保存原始文件副本到仓库；日志落盘前必须过 log_sanitize.py
