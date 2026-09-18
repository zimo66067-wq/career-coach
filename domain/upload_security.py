"""Defensive validation for untrusted resume and job-description uploads."""
from pathlib import Path, PurePosixPath
import zipfile


MAX_PDF_PAGES = 50
MAX_ARCHIVE_ENTRIES = 500
MAX_ARCHIVE_UNCOMPRESSED = 25 * 1024 * 1024
MAX_ARCHIVE_MEMBER = 10 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100


class UploadSecurityError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _reject(code, message):
    raise UploadSecurityError(code, message)


def _validate_pdf(path):
    from pypdf import PdfReader

    with open(path, "rb") as handle:
        if handle.read(5) != b"%PDF-":
            _reject("file_signature_mismatch", "文件扩展名与实际 PDF 格式不一致。")
    try:
        reader = PdfReader(str(path), strict=True)
        if reader.is_encrypted:
            _reject("encrypted_file", "不支持加密或设有密码的 PDF。")
        page_count = len(reader.pages)
    except UploadSecurityError:
        raise
    except Exception as exc:
        raise UploadSecurityError("malformed_file", "PDF 文件结构异常或已经损坏。") from exc
    if page_count > MAX_PDF_PAGES:
        _reject("too_many_pages", f"PDF 最多支持 {MAX_PDF_PAGES} 页。")
    return {"page_count": page_count}


def _safe_member_name(name):
    normalized = str(name or "").replace("\\", "/")
    member = PurePosixPath(normalized)
    if not normalized or normalized.startswith("/") or ".." in member.parts:
        return False
    if member.parts and ":" in member.parts[0]:
        return False
    return True


def _validate_docx(path):
    with open(path, "rb") as handle:
        if handle.read(4) not in {b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"}:
            _reject("file_signature_mismatch", "文件扩展名与实际 DOCX 格式不一致。")
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                _reject("archive_too_complex", "DOCX 内部文件数量异常。")
            total_size = 0
            names = set()
            for info in entries:
                name = info.filename.replace("\\", "/")
                lowered = name.lower()
                if not _safe_member_name(name):
                    _reject("unsafe_archive_path", "DOCX 包含不安全的内部路径。")
                if info.flag_bits & 0x1:
                    _reject("encrypted_file", "不支持加密的 DOCX。")
                if (
                    lowered.endswith("vbaproject.bin")
                    or lowered.startswith("word/activex/")
                    or lowered.startswith("word/embeddings/")
                ):
                    _reject("active_content", "DOCX 包含宏、ActiveX 或嵌入对象，已拒绝处理。")
                total_size += int(info.file_size)
                if info.file_size > MAX_ARCHIVE_MEMBER:
                    _reject("archive_member_too_large", "DOCX 内部单个文件过大。")
                if info.file_size > 1024 * 1024:
                    ratio = info.file_size / max(1, info.compress_size)
                    if ratio > MAX_COMPRESSION_RATIO:
                        _reject("compression_bomb", "DOCX 压缩比例异常，已拒绝处理。")
                names.add(name)
            if total_size > MAX_ARCHIVE_UNCOMPRESSED:
                _reject("archive_too_large", "DOCX 解压后的内容过大。")
            required = {"[Content_Types].xml", "word/document.xml"}
            if not required.issubset(names):
                _reject("malformed_file", "DOCX 缺少必要的文档结构。")
    except UploadSecurityError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise UploadSecurityError("malformed_file", "DOCX 文件结构异常或已经损坏。") from exc
    return {"entry_count": len(entries), "uncompressed_bytes": total_size}


def _validate_txt(path):
    data = Path(path).read_bytes()
    if b"\x00" in data:
        _reject("binary_text_file", "TXT 文件包含二进制内容。")
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # The extractor supports a small set of Chinese legacy encodings, but
        # binary-looking input must not be accepted as a text document.
        printable = sum(byte in b"\t\n\r" or 32 <= byte <= 126 or byte >= 128 for byte in data)
        if data and printable / len(data) < 0.9:
            _reject("binary_text_file", "TXT 文件不像可读文本。")
    return {}


def validate_upload(path, extension):
    """Validate file signature, container structure and expansion bounds."""
    extension = str(extension or "").lower()
    if extension == ".pdf":
        return _validate_pdf(path)
    if extension == ".docx":
        return _validate_docx(path)
    if extension == ".txt":
        return _validate_txt(path)
    _reject("unsupported_file_type", "不支持的文件格式。")
