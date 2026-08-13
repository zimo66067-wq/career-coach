# -*- coding: utf-8 -*-
"""ocr_provider.py · 扫描件/图片型 PDF 的 OCR 兜底（阶段2）

策略：
  1. pypdf 优先提取可复制文本层；文本为空时视为潜在扫描件。
  2. detect_scanned_pdf：无文本层且页面含像素内容 -> 判为扫描件。
  3. ocr_pdf：配置 OCR_API_KEY/OCR_SECRET_KEY 时调用百度 OCR general_basic
     逐页识别；未配置或失败时返回结构化错误，由上层给出可操作引导。

安全：只把密钥放环境变量；不落盘图片；OCR 文本仅用于本次解析。
"""
import base64
import io
import json
import logging
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger("ocr_provider")

BAIDU_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
BAIDU_OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"

_token_cache = {"token": None, "expires_at": 0}


def ocr_configured():
    """是否已配置百度 OCR 密钥。"""
    return bool(os.environ.get("OCR_API_KEY") and os.environ.get("OCR_SECRET_KEY"))


def _baidu_access_token():
    """获取（并缓存）百度 OCR access_token；失败返回 None。"""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]
    api_key = os.environ.get("OCR_API_KEY", "")
    secret = os.environ.get("OCR_SECRET_KEY", "")
    if not api_key or not secret:
        return None
    try:
        url = BAIDU_TOKEN_URL + "?" + urlencode({
            "grant_type": "client_credentials",
            "client_id": api_key,
            "client_secret": secret,
        })
        req = Request(url, method="POST")
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        token = data.get("access_token")
        if not token:
            return None
        _token_cache["token"] = token
        _token_cache["expires_at"] = now + int(data.get("expires_in", 2592000))
        return token
    except (HTTPError, URLError, OSError, ValueError) as exc:
        logger.warning("获取 OCR access_token 失败：%s", exc)
        return None


def ocr_image(image_bytes, provider="baidu"):
    """识别单张图片。返回 {ok, text?, error?, message?}。"""
    if provider == "baidu":
        return _ocr_baidu(image_bytes)
    return {"ok": False, "error": "unsupported", "message": "不支持的 OCR 服务：%s" % provider}


def _ocr_baidu(image_bytes):
    if not ocr_configured():
        return {
            "ok": False,
            "error": "unsupported",
            "message": "未配置 OCR_API_KEY/OCR_SECRET_KEY，无法识别扫描件；请粘贴文字或配置 OCR 后重试。",
        }
    try:
        token = _baidu_access_token()
        if not token:
            return {"ok": False, "error": "ocr_auth", "message": "OCR 鉴权失败，请检查 OCR_API_KEY/OCR_SECRET_KEY。"}
        payload = urlencode({
            "image": base64.b64encode(image_bytes).decode("ascii"),
            "detect_direction": "true",
            "paragraph": "true",
        }).encode("utf-8")
        req = Request(
            BAIDU_OCR_URL + "?access_token=" + token,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("error_code"):
            return {
                "ok": False,
                "error": "ocr_failed",
                "message": "OCR 服务返回错误：%s" % data.get("error_msg", "未知"),
            }
        lines = [w.get("words", "") for w in data.get("words_result", []) if w.get("words")]
        return {"ok": True, "text": "\n".join(lines)}
    except HTTPError as exc:
        return {"ok": False, "error": "ocr_failed", "message": "OCR 服务 HTTP %s" % exc.code}
    except (URLError, OSError, ValueError) as exc:
        return {"ok": False, "error": "ocr_failed", "message": "OCR 网络错误：%s" % exc}


def _page_has_pixels(page, dark_threshold=240, dark_ratio=0.01):
    """粗略判断页面是否含像素内容（扫描件特征：非纯白）。"""
    try:
        bitmap = page.render(scale=1.0)
        image = bitmap.to_pil().convert("L")
        width, height = image.size
        step_x = max(1, width // 40)
        step_y = max(1, height // 40)
        dark = 0
        total = 0
        for x in range(0, width, step_x):
            for y in range(0, height, step_y):
                total += 1
                if image.getpixel((x, y)) < dark_threshold:
                    dark += 1
        return total > 0 and (dark / total) > dark_ratio
    except Exception as exc:  # noqa: BLE001
        logger.warning("_page_has_pixels 失败：%s", exc)
        return False


def detect_scanned_pdf(path, pages_to_probe=2):
    """判断 PDF 是否扫描件：文本层为空且页面含像素内容。"""
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        page_text = "".join((page.extract_text() or "") for page in reader.pages[:pages_to_probe]).strip()
        if page_text:
            return False
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(path)
        n = min(pages_to_probe, len(pdf))
        for i in range(n):
            if _page_has_pixels(pdf[i]):
                return True
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("detect_scanned_pdf 失败：%s", exc)
        return False


def ocr_pdf(path, pages_to_probe=6):
    """对扫描件 PDF 逐页 OCR。返回 {ok, text?, error?, message?}。"""
    if not ocr_configured():
        return {
            "ok": False,
            "error": "unsupported",
            "message": "未配置 OCR_API_KEY/OCR_SECRET_KEY，无法识别扫描件；请粘贴文字或配置 OCR 后重试。",
        }
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(path)
        parts = []
        for i in range(min(pages_to_probe, len(pdf))):
            page = pdf[i]
            bitmap = page.render(scale=2.0)
            buffer = io.BytesIO()
            bitmap.to_pil().convert("RGB").save(buffer, format="PNG")
            result = ocr_image(buffer.getvalue(), "baidu")
            if not result.get("ok"):
                return result
            if result.get("text"):
                parts.append(result["text"])
        return {"ok": True, "text": "\n\n".join(parts)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "ocr_failed", "message": "OCR 处理失败：%s" % exc}
