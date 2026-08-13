# -*- coding: utf-8 -*-
"""test_ocr_provider.py · 阶段2：OCR 兜底（provider + 扫描件上传路径）"""
import io
import json
import tempfile
import uuid
from pathlib import Path

import pytest

import api.index as api_module
import tools.ocr_provider as ocr


def raw_client(monkeypatch):
    monkeypatch.setenv("DUMATE_CONSENT_SECRET", "test-consent-secret")
    monkeypatch.delenv("DUMATE_CONSENT_MAX_AGE_SECONDS", raising=False)
    if not hasattr(monkeypatch, "_career_ocr_test_db"):
        monkeypatch._career_ocr_test_db = str(
            Path(tempfile.mkdtemp(prefix="career_ocr_test_")) / ("test_%s.db" % uuid.uuid4().hex[:8])
        )
    monkeypatch.setenv("RESUME_DB_PATH", monkeypatch._career_ocr_test_db)
    api_module.app.config.update(TESTING=True)
    return api_module.app.test_client()


def consented_client(monkeypatch):
    raw = raw_client(monkeypatch)
    consent = raw.post("/api/wf01/consent", json={"accepted": True})
    assert consent.status_code == 200
    token = consent.json["consent_token"]

    class _Client:
        def post(self, *args, **kwargs):
            headers = dict(kwargs.pop("headers", {}) or {})
            headers.setdefault("X-Consent-Token", token)
            return raw.post(*args, headers=headers, **kwargs)

    return _Client()


def _blank_pdf_bytes():
    """无文本层的最小合法 PDF（触发扫描件/图片型判定路径）。"""
    content = "BT /F1 12 Tf 20 150 Td () Tj ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        "<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
    ]
    parts, offsets = [], []
    header = "%PDF-1.4\n"
    parts.append(header)
    pos = len(header.encode("latin-1"))
    for i, body in enumerate(objs, start=1):
        offsets.append(pos)
        chunk = "%d 0 obj\n%s\nendobj\n" % (i, body)
        parts.append(chunk)
        pos += len(chunk.encode("latin-1"))
    xref_pos = pos
    xref = "xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        xref += "%010d 00000 n \n" % off
    trailer = "trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref_pos)
    return ("".join(parts) + xref + trailer).encode("latin-1")


def _text_pdf_bytes(text):
    """带文本层的最小合法 PDF。"""
    safe = "".join(ch if 32 <= ord(ch) < 127 and ch not in "()" else "?" for ch in text[:80])
    content = "BT /F1 12 Tf 20 150 Td (%s) Tj ET" % safe
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        "<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
    ]
    parts, offsets = [], []
    header = "%PDF-1.4\n"
    parts.append(header)
    pos = len(header.encode("latin-1"))
    for i, body in enumerate(objs, start=1):
        offsets.append(pos)
        chunk = "%d 0 obj\n%s\nendobj\n" % (i, body)
        parts.append(chunk)
        pos += len(chunk.encode("latin-1"))
    xref_pos = pos
    xref = "xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        xref += "%010d 00000 n \n" % off
    trailer = "trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref_pos)
    return ("".join(parts) + xref + trailer).encode("latin-1")


# ---------- provider 单元 ----------

def test_ocr_unconfigured_returns_unsupported(monkeypatch):
    monkeypatch.delenv("OCR_API_KEY", raising=False)
    monkeypatch.delenv("OCR_SECRET_KEY", raising=False)
    assert ocr.ocr_configured() is False
    result = ocr.ocr_image(b"image-bytes")
    assert result["ok"] is False
    assert result["error"] == "unsupported"
    pdf_result = ocr.ocr_pdf("/nonexistent.pdf")
    assert pdf_result["error"] == "unsupported"


def test_baidu_ocr_success(monkeypatch):
    monkeypatch.setenv("OCR_API_KEY", "test-key")
    monkeypatch.setenv("OCR_SECRET_KEY", "test-secret")
    monkeypatch.setattr(ocr, "_baidu_access_token", lambda: "token-1")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(
                {"words_result": [{"words": "张三"}, {"words": "三年后端开发"}]}
            ).encode("utf-8")

    monkeypatch.setattr(ocr, "urlopen", lambda *args, **kwargs: FakeResponse())
    result = ocr.ocr_image(b"png-bytes")
    assert result["ok"] is True
    assert "张三" in result["text"]
    assert "后端开发" in result["text"]


def test_baidu_ocr_error_code(monkeypatch):
    monkeypatch.setenv("OCR_API_KEY", "test-key")
    monkeypatch.setenv("OCR_SECRET_KEY", "test-secret")
    monkeypatch.setattr(ocr, "_baidu_access_token", lambda: "token-1")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"error_code": 17, "error_msg": "Open api daily request limit reached"}).encode("utf-8")

    monkeypatch.setattr(ocr, "urlopen", lambda *args, **kwargs: FakeResponse())
    result = ocr.ocr_image(b"png-bytes")
    assert result["ok"] is False
    assert result["error"] == "ocr_failed"


def test_detect_scanned_pdf_text_layer(tmp_path):
    text_pdf = tmp_path / "text.pdf"
    text_pdf.write_bytes(_text_pdf_bytes("Resume backend developer Go MySQL Redis"))
    assert ocr.detect_scanned_pdf(str(text_pdf)) is False


def test_detect_scanned_pdf_blank_page(tmp_path):
    blank_pdf = tmp_path / "blank.pdf"
    blank_pdf.write_bytes(_blank_pdf_bytes())
    # 空白页无像素内容，不应误判为扫描件
    assert ocr.detect_scanned_pdf(str(blank_pdf)) is False


# ---------- 上传接口 ----------

def test_upload_scanned_pdf_without_ocr_returns_clear_error(monkeypatch):
    monkeypatch.delenv("OCR_API_KEY", raising=False)
    monkeypatch.delenv("OCR_SECRET_KEY", raising=False)
    response = consented_client(monkeypatch).post(
        "/api/wf01/upload",
        data={"file": (io.BytesIO(_blank_pdf_bytes()), "scanned.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    body = response.json
    assert body["error"] == "scanned_pdf"
    assert "扫描件" in body["message"]


def test_upload_scanned_pdf_ocr_success(monkeypatch):
    monkeypatch.setenv("OCR_API_KEY", "test-key")
    monkeypatch.setenv("OCR_SECRET_KEY", "test-secret")
    ocr_text = (
        "张三，三年后端开发经验，精通 Python、Go 与 MySQL，负责订单与支付系统，"
        "主导过日活十万级服务的稳定性建设，具备完整的项目交付与团队协作能力。"
    )
    monkeypatch.setattr(api_module, "ocr_pdf", lambda path: {"ok": True, "text": ocr_text})
    response = consented_client(monkeypatch).post(
        "/api/wf01/upload",
        data={"file": (io.BytesIO(_blank_pdf_bytes()), "scanned.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    body = response.json
    assert body["resumeText"] == ocr_text
    assert body["session_id"]


def test_upload_scanned_pdf_ocr_failure_message(monkeypatch):
    monkeypatch.setenv("OCR_API_KEY", "test-key")
    monkeypatch.setenv("OCR_SECRET_KEY", "test-secret")
    monkeypatch.setattr(
        api_module, "ocr_pdf", lambda path: {"ok": False, "error": "ocr_failed", "message": "OCR 服务异常"}
    )
    response = consented_client(monkeypatch).post(
        "/api/wf01/upload",
        data={"file": (io.BytesIO(_blank_pdf_bytes()), "scanned.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    assert response.json["error"] == "scanned_pdf"
    assert "OCR 服务异常" in response.json["message"]
