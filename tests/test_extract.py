# -*- coding: utf-8 -*-
"""test_extract.py · 现场生成 docx/pdf 并验证提取"""
import os

import pytest

import extract_text


def _make_docx(path, text):
    import docx
    doc = docx.Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    doc.save(str(path))


def _make_pdf(path, text):
    # 手写最小合法 PDF（Helvetica 单行文本 + 正确 xref），不依赖第三方生成库
    safe = "".join(c if 32 <= ord(c) < 127 and c not in "()" else "?" for c in text[:80])
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
    with open(str(path), "w", encoding="latin-1") as f:
        f.write("".join(parts) + xref + trailer)


def test_extract_txt(tmp_path, resume_txts):
    src = tmp_path / "r.txt"
    text = resume_txts["resume-01-swe.txt"]
    src.write_text(text, encoding="utf-8")
    out = extract_text.extract_txt(str(src))
    assert "订单" in out and len(out) > 100


def test_extract_docx_roundtrip(tmp_path, resume_txts):
    text = resume_txts["resume-01-swe.txt"]
    docx_path = tmp_path / "r.docx"
    _make_docx(docx_path, text)
    out = extract_text.extract_docx(str(docx_path))
    assert "订单" in out
    assert "800ms" in out


def test_extract_docx_zip_fallback(tmp_path, resume_txts):
    text = resume_txts["resume-01-swe.txt"]
    docx_path = tmp_path / "r.docx"
    _make_docx(docx_path, text)
    out = extract_text.extract_docx_zip(str(docx_path))
    assert "订单" in out


def test_extract_pdf_roundtrip(tmp_path):
    pdf_path = tmp_path / "r.pdf"
    _make_pdf(pdf_path, "Resume backend developer Go MySQL Redis order service")
    out = extract_text.extract_pdf(str(pdf_path))
    assert "Resume" in out


def test_scanned_pdf_exits_code2(tmp_path):
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    pdf_path = tmp_path / "scan.pdf"
    with open(str(pdf_path), "wb") as f:
        writer.write(f)
    with pytest.raises(SystemExit) as e:
        extract_text.extract_pdf(str(pdf_path))
    assert e.value.code == 2
