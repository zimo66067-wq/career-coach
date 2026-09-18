# -*- coding: utf-8 -*-
"""文本校验与上传文件提取（Phase 7c 从 `api/index.py` 逐字拆出）。

两条入口，一条共同规则：

* 粘贴文本走 `validate_text` / `validate_job_text`；
* 上传文件走 `read_uploaded_*` → 落临时文件 → 安全校验 → 按扩展名提取 → 同一套长度校验。

**长度规则只有一份**（`validate_document_text`）：20 ≤ 字符数 ≤ 20 万。两条入口共用它，
所以"粘贴 19 字被拒"和"上传 19 字的 txt 被拒"必然同口径。

## 打桩点（切分后位置变了）

`extract_txt` / `extract_docx` / `extract_pdf` / `validate_upload` / `ocr_pdf` 是
**测试的打桩点** —— 边界用例没法真的造一个 10 MB 的 PDF，只能把这些替换掉，再看
上传路径怎么反应（`tests/test_api_boundary.py`、`tests/test_ocr_provider.py`）。

它们从 `api.index` 搬到了这里，**打桩位置必须跟着一起搬**（`api.validation.extract_txt`）。
打在 `api.index` 上是"静默失效"：`monkeypatch.setattr` 会因为属性还在而成功，
但上传路径用的是本模块的绑定，测试就变成了空判 —— 这正是 `tests/test_layering.py`
花一整节讲的那类坑。

`ocr_pdf` 的调用点在 `SystemExit` 分支上：PDF 提取器发现"扫描件无文字"时会以
`SystemExit` 退出，这里接住并尝试 OCR，失败则明确告诉用户"这是图片型 PDF"，
而不是含糊地报"无法读取"。
"""
import os
import tempfile
from pathlib import Path

from flask import request

from tools.api_errors import ApiError
from tools.extract_text import extract_docx, extract_pdf, extract_txt
from tools.ocr_provider import ocr_pdf
from tools.upload_security import UploadSecurityError, validate_upload

from api.constants import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_BYTES,
    MAX_TEXT_CHARS,
    MIN_TEXT_CHARS,
)


def validate_document_text(value, label, error_code):
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) < MIN_TEXT_CHARS:
        raise ApiError(error_code, "%s正文至少需要 20 个字符。" % label, 422)
    if len(text) > MAX_TEXT_CHARS:
        raise ApiError("payload_too_large", "%s正文不能超过 20 万个字符。" % label, 413)
    return text


def validate_text(value):
    return validate_document_text(value, "简历", "invalid_resume_text")


def validate_job_text(value):
    return validate_document_text(value, "职位说明（JD）", "invalid_jd_text")


def read_uploaded_document(label, error_code):
    """Extract and validate an uploaded PDF/DOCX/TXT. Returns (text, filename, ext, size)."""
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        raise ApiError("missing_file", "请选择要上传的 PDF、DOCX 或 TXT %s。" % label, 422)

    extension = Path(uploaded.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ApiError("unsupported_file_type", "仅支持 PDF、DOCX 或 TXT 格式。", 415)

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temporary_file:
            temporary_path = temporary_file.name
        uploaded.save(temporary_path)
        file_size = os.path.getsize(temporary_path)
        if file_size > MAX_FILE_BYTES:
            raise ApiError("payload_too_large", "文件不能超过 10 MB。", 413)
        validate_upload(temporary_path, extension)
        if extension == ".pdf":
            text = extract_pdf(temporary_path)
        elif extension == ".docx":
            text = extract_docx(temporary_path)
        else:
            text = extract_txt(temporary_path)
        safe_filename = ("resume" if error_code == "invalid_resume_text" else "job-description") + extension
        return validate_document_text(text, label, error_code), safe_filename, extension, file_size
    except ApiError:
        raise
    except UploadSecurityError as exc:
        raise ApiError(exc.code, exc.message, 422)
    except SystemExit:
        if extension == ".pdf":
            # 扫描件 OCR 兜底：配置 OCR_API_KEY/OCR_SECRET_KEY 时自动逐页识别
            try:
                ocr_result = ocr_pdf(temporary_path)
            except Exception:  # noqa: BLE001
                ocr_result = {"ok": False, "error": "ocr_failed", "message": "OCR 处理异常"}
            if ocr_result.get("ok") and str(ocr_result.get("text") or "").strip():
                text = str(ocr_result["text"]).strip()
                return validate_document_text(text, label, error_code), uploaded.filename, extension, file_size
            detail = str(ocr_result.get("message") or "")
            raise ApiError(
                "scanned_pdf",
                "该 PDF 是扫描件/图片型，无法直接提取文字。%s请改为可复制文字的 PDF、DOCX、TXT 或直接粘贴正文。" % (detail + ("，" if detail else "")),
                422,
            )
        raise ApiError("unreadable_file", "未能读取该文件，请改为可复制文字的 PDF、DOCX、TXT 或直接粘贴正文。", 422)
    except Exception:
        raise ApiError("unreadable_file", "未能读取该文件，请确认文件未损坏后重试。", 422)
    finally:
        if temporary_path:
            try:
                os.remove(temporary_path)
            except OSError:
                pass


def read_uploaded_resume():
    return read_uploaded_document("简历", "invalid_resume_text")


def read_uploaded_job():
    return read_uploaded_document("职位说明（JD）", "invalid_jd_text")
