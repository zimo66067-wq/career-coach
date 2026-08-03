#!/usr/bin/env python3
"""P0-05 官方链接可达性批量检查"""
import json, time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PROJECT = Path(__file__).resolve().parent.parent
EVIDENCE = PROJECT / "deliverables/wf-evidence-20260803"

urls = [
    {"url": "https://qianfan.baidubce.com/v2", "source": "model_router.py", "note": "千帆 API Base URL"},
    {"url": "https://aip.baidubce.com/oauth/2.0/token", "source": "match_requirements.py", "note": "千帆 OAuth 鉴权"},
    {"url": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenniu/embedding_v1", "source": "match_requirements.py", "note": "旧版千帆 embedding"},
    {"url": "https://qianfan.baidubce.com/v2/embeddings", "source": "test_qianfan_embedding.py", "note": "新版千帆 embedding-v1"},
    {"url": "https://qianfan.baidubce.com/v2/chat/completions", "source": "test_new_tools.py", "note": "千帆 Chat Completions"},
    {"url": "https://api.jina.ai/v1/embeddings", "source": "test_embedding_comprehensive.py", "note": "Jina AI 备选 embedding"},
    {"url": "https://dumate.baidu.com/asr", "source": "voice_handler.py", "note": "DuMate ASR 接口"},
    {"url": "https://open.bigmodel.cn/", "source": "MEMORY.md", "note": "智谱 AI 开放平台"},
    {"url": "https://jina.ai/embeddings/", "source": "test_embedding_comprehensive.py", "note": "Jina AI Embedding 文档"},
]

results = []
for item in urls:
    url = item["url"]
    t0 = time.time()
    http_code = ""
    reason = ""
    method = "HEAD"

    # 第一试：HEAD
    try:
        req = Request(url, method="HEAD")
        with urlopen(req, timeout=10) as resp:
            http_code = str(resp.status)
            reason = resp.reason
    except HTTPError as e:
        http_code = str(e.code)
        reason = e.reason
    except URLError as e:
        http_code = "ERR"
        reason = str(e.reason)
    except Exception as e:
        http_code = "ERR"
        reason = str(e)

    # 第二试：如果 HEAD 返回 400/404/405/501，换 GET 探测
    if http_code in ("400", "404", "405", "501"):
        method = "GET"
        try:
            req = Request(url, method="GET")
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            with urlopen(req, timeout=10) as resp:
                http_code = str(resp.status)
                reason = resp.reason
        except HTTPError as e:
            http_code = str(e.code)
            reason = e.reason
        except URLError as e:
            http_code = "ERR"
            reason = str(e.reason)
        except Exception as e:
            http_code = "ERR"
            reason = str(e)

    elapsed = round(time.time() - t0, 2)

    # 可达判定：2xx / 3xx / 401(需鉴权) / 403(Cloudflare拦截但域名可达)
    reachable = http_code in ("200", "201", "204", "301", "302", "307", "308", "401", "403")
    needs_auth = http_code == "401"
    head_mismatch = method == "GET"

    results.append({
        "url": url,
        "source": item["source"],
        "note": item["note"],
        "http_code": http_code,
        "reason": reason,
        "elapsed_s": elapsed,
        "reachable": reachable,
        "needs_auth": needs_auth,
        "head_mismatch": head_mismatch,
        "method": method,
    })

# 统计
ok = sum(1 for r in results if r["reachable"])
need_key = sum(1 for r in results if r["needs_auth"])
head_fail = sum(1 for r in results if r["head_mismatch"])

report = {
    "p0-05_link_check": {
        "date": datetime.now().isoformat(),
        "summary": {
            "total": len(results),
            "reachable": ok,
            "needs_auth": need_key,
            "head_mismatch": head_fail,
            "unreachable": len(results) - ok,
        },
        "results": results,
    }
}

report_path = EVIDENCE / "p0-05-link-check-report.json"
with open(report_path, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f"P0-05 链接检查完成")
print(f"  总数: {len(results)}")
print(f"  可达: {ok}")
print(f"  需鉴权: {need_key}")
print(f"  HEAD不匹配(换GET成功): {head_fail}")
print(f"  不可达: {len(results) - ok}")
print(f"  报告: {report_path}")
print()
for r in results:
    icon = "✅" if r["reachable"] else "❌"
    key_note = " [需API key]" if r["needs_auth"] else ""
    head_note = " [HEAD→GET]" if r["head_mismatch"] else ""
    print(f"  {icon} [{r['method']}] [{r['http_code']} {r['reason']}] {r['url']}{key_note}{head_note}")
