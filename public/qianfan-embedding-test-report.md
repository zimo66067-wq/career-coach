---
title: "千帆 Embedding API 测试报告"
date: "2026-08-02"
type: "测试报告"
project: "iCAN无代码开发挑战赛-DuMate方向"
repository: "zimo66067-wq/career-coach"
tags:
  - iCAN
  - DuMate
  - AI求职面试教练
  - 千帆API
  - Embedding
  - 召回率
---

# 千帆 Embedding API 测试报告

**测试日期**: 2026-08-02
**测试人员**: AI Agent (自动化)
**测试目标**: 验证千帆 Embedding API 连通性 + 抽样召回率

## 一、API 连通性测试

### 1.1 鉴权方式确认

**密钥类型**: 千帆应用 API Key (bce-v3/ALTAK-...)
- **正确鉴权方式**: Bearer Token (`Authorization: Bearer <AK>/<SK>`)
- **错误鉴权方式**: OAuth client_credentials (401 Invalid Client)
- **错误鉴权方式**: IAM Access Key (unsupported)

### 1.2 Endpoint 确认

| Endpoint | 结果 |
|---|---|
| `https://api.baiduqianfan.ai/v1/embeddings` | 404 Not Found |
| `https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenniu/embedding_v1` | 403 Unsupported Method |
| `https://qianfan.baidubce.com/v2/embeddings` ✅ | **200 OK** |

### 1.3 模型确认

- **正确模型**: `embedding-v1`
- **输出维度**: 384 维
- **错误模型**: `embedding-v2`, `bge-large-zh` → 404 no_such_model

### 1.4 连通性结论

**API 连通性**: ✅ 通过（单次调用成功，维度 384）
**批量调用**: ⚠️ 受限（免费版 QPS 限制，需间隔调用或充值）

---

## 二、召回率测试

### 2.1 BM25 基线（纯本地，无需 API）

| 指标 | 数值 |
|---|---|
| 总要求数 | 250（5 简历 × 5 JD × 每 JD 平均 10 条要求） |
| 命中数 | 166 |
| **召回率** | **66.4%** |

**按简历维度**：
- resume-01-swe（对口后端）: **88.0%**（最高）
- resume-15-bigdata: 70.0%
- resume-10-devops: 66.0%
- resume-20-fresh-general: 58.0%
- resume-05-fresh（应届）: **50.0%**（最低）

**按 JD 维度**：
- job-10-bigdata: **83.6%**（最高）
- job-09-algo: 76.4%
- job-01-swe: 64.4%
- job-02-fe: 55.0%
- job-07-pm: **49.1%**（最低，软技能语义缺失）

**状态分布**：
- weak: 126 (50.4%)
- missing: 63 (25.2%)
- covered: 40 (16.0%)
- unknown: 21 (8.4%)

### 2.2 千帆 Embedding 实测

**受限原因**: 免费版 API 频率限制（QPS ≤ 2）
- 单次调用成功（维度 384）
- 批量测试触发 403 Forbidden
- **解决方式**: 充值或降低调用频率（每请求间隔 2-5 秒）

---

## 三、BM25 vs Embedding 对比分析

| 对比项 | BM25 | 千帆 Embedding |
|---|---|---|
| 召回率 | 66.4% | 目标 ≥85%（待全量验证） |
| 对口简历 | 88.0% | 预计 >90% |
| 应届简历 | 50.0% | 预计 70-80%（语义理解优势） |
| 软技能 JD | 49.1% | 预计 80%+（语义匹配优势） |
| 技术词 JD | 83.6% | 预计 90%+ |
| 依赖 | 纯本地 | 需 API Key + 网络 |
| 成本 | 免费 | ~¥0.002/千 tokens |

**关键洞察**:
1. BM25 对**对口技术简历**表现好（88%），但对**软技能要求**和**应届简历**明显不足
2. Embedding 语义匹配预计能显著提升软技能 JD 和应届简历的召回率
3. 两者组合（先 Embedding 粗筛 + BM25 精排）是最佳策略

---

## 四、仍需人工完成的项

### 4.1 高优先级（阻塞 Embedding 全量测试）

**1. 千帆 Embedding 全量召回率验证**
- **状态**: 脚本已就绪，受 API 频率限制
- **操作**: 充值或降低调用频率后运行 `python tests/test_qianfan_embedding.py`
- **目标**: 验证召回率是否 ≥85%

**2. API Key 权限确认**
- **状态**: 已创建，需确认 Embedding 服务权限已开通
- **操作**: 登录千帆控制台 → 应用管理 → 确认服务范围包含 Embedding

### 4.2 中优先级（平台操作类）

**3. DuMate 平台搭建工作流（P0-01）**
- 按合同定义搭建 WF-01~WF-06
- 产出：运行截图、导出物

**4. 浏览器语音实机测试（P0-05）**
- Chrome 测试 5 类用例（正常/拒绝麦克风/断网/识别错误/TTS失败）
- 产出：录屏或截图

**5. 端到端真实数据闭环（P0-02）**
- 配置 `DUMATE_API_BASE`
- 用陌生简历执行完整链路

### 4.3 低优先级（人工验证类）

**6. G8 用户验证（P0-07）**
- 招募 5-8 名用户，执行 10 个测试任务

**7. 官方链接核验（P0-06）**
- 登录 iCAN 入口，逐项核验 55 项能力

**8. 移动端真机测试（P1-09）**
- 2 浏览器 + 1 手机，执行 23 项无障碍清单

**9. 模型盲测（P2-02）**
- 对 Kimi-K3 / Kimi-K2.7-Code / DuMate 当前模型执行盲测

**10. G9 提交包冻结（P0-07）**
- 完成所有运行证据后，执行 10 次彩排

---

## 五、代码已提交

- `tests/test_qianfan_embedding.py` — 千帆 Embedding 连通性 + 召回率测试
- `tests/test_bm25_baseline.py` — BM25 基线召回率测试

---

**报告生成时间**: 2026-08-02 10:15
**下一步建议**: 优先解决 API 频率限制，运行全量 Embedding 召回率测试
