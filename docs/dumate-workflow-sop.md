---
title: DuMate 六工作流平台搭建 SOP
date: 2026-08-02
type: 标准操作手册
project: iCAN无代码开发挑战赛-DuMate方向
repository: zimo66067-wq/career-coach
status: 可执行
tags:
  - DuMate
  - 工作流
  - SOP
  - P0-01
  - iCAN
---

# DuMate 六工作流平台搭建 SOP

**目标：** 在 DuMate 平台上逐个搭建 WF-01 ~ WF-06，使其可运行、可截图、可验收。
**前置条件：** DuMate 平台账号已开通，浏览器为 Chrome 120+，本仓库已 clone 到本地。

## 通用搭建原则

1. 每个工作流对应一个 DuMate 对话任务，命名格式 `career-coach-WF-0X-<简称>`
2. 每个工作流必须包含：触发条件、工具调用链、状态转换、降级路径、验收命令
3. 所有工具调用的 Python 脚本路径以仓库根目录为基准
4. 变量绑定使用 DuMate 平台的变量系统，非硬编码
5. 搭建完成后必须运行验收命令并保存截图

## WF-01：材料接收与解析

### 平台配置

| 配置项 | 值 |
|--------|-----|
| 任务名称 | `career-coach-WF-01-intake` |
| 触发条件 | 用户上传文件（PDF/DOCX/TXT）或粘贴文本，含"诊断简历""分析简历"等意图 |
| 输入变量 | `resume_file_path`（文件模式）/ `resume_raw_text`（粘贴模式） |
| 输出变量 | `resume_clean_text`（脱敏后纯文本） |

### 搭建步骤

1. **创建对话任务**，命名为 `career-coach-WF-01-intake`
2. **设置意图识别**：关键词包含"简历""诊断""分析""上传"
3. **配置 CONSENT 节点**：展示"我将对你的简历进行去标识化处理，仅用于本次诊断，不保存原始文件。是否同意？"，等待用户确认
4. **配置工具调用链**：

```
# 文件模式
步骤1: python tools/extract_text.py --input {{resume_file_path}} --output /tmp/resume_raw.txt
步骤2: python tools/deidentify.py --input /tmp/resume_raw.txt --output /tmp/resume_clean.txt
步骤3: 验证 /tmp/resume_clean.txt 尾部含 "pii_removed:true"
步骤4: 正则扫描确认无 PII 残留
```

5. **配置状态转换**：INIT -> CONSENT -> EXTRACTING -> DEIDENTIFYING -> RESUME_READY（或 PARSE_FAILED）
6. **配置降级路径**：PDF 提取为空 -> 引导粘贴；去标识化残留 PII -> 阻断并提示

### 验收命令

```bash
python tools/extract_text.py --input tests/fixtures-synthetic/resumes/resume-01-swe.txt --output /tmp/wf01_raw.txt
python tools/deidentify.py --input /tmp/wf01_raw.txt --output /tmp/wf01_clean.txt
grep -c "pii_removed:true" /tmp/wf01_clean.txt  # 应为 1
grep -cE "1[3-9][0-9]{9}" /tmp/wf01_clean.txt   # 应为 0
python -m pytest tests/test_extract.py tests/test_deidentify.py -v
```

### 截图清单

- [ ] CONSENT 节点对话截图
- [ ] 文件上传 -> 提取成功截图
- [ ] 脱敏后文本展示截图（前 100 字）
- [ ] 降级路径：粘贴文本模式截图
- [ ] 降级路径：PDF 扫描件提示截图

---

## WF-02：简历诊断

### 平台配置

| 配置项 | 值 |
|--------|-----|
| 任务名称 | `career-coach-WF-02-diagnosis` |
| 触发条件 | WF-01 输出 `resume_clean_text`，用户确认进入诊断 |
| 输入变量 | `resume_clean_text`（来自 WF-01） |
| 输出变量 | `resume_profile_json`（结构化诊断结果） |

### 搭建步骤

1. **创建对话任务**，命名为 `career-coach-WF-02-diagnosis`
2. **配置模型路由**：任务类型 `resume_diagnosis`，temperature=0.1，max_tokens=4096，timeout=30s
3. **配置主路径**：

```
步骤1: 调用 model_router.call("resume_diagnosis", resume_clean_text)
步骤2: 解析模型输出为 ResumeProfile JSON
步骤3: 校验 JSON 符合 contracts/resume-profile.schema.json
```

4. **配置降级路径**：主模型失败 -> 使用 DEGRADED_OUTPUTS["resume_diagnosis"]，标记 `degraded=true`
5. **配置评分**：子分数按 `contracts/scoring.md` F1 公式计算 R 分

### 验收命令

```bash
python -c "
import sys; sys.path.insert(0, 'tools')
from model_router import ModelRouter, DEGRADED_OUTPUTS
class TestRouter(ModelRouter):
    def _try_call(self, *a, **kw): raise RuntimeError('test degraded')
r = TestRouter(primary_model='test').call('resume_diagnosis', 'test input')
assert r['status'] == 'degraded'
assert r['degraded'] is True
print('WF-02 degradation test passed')
"
python tools/validate_schema.py --schema contracts/resume-profile.schema.json --instance tests/fixtures-synthetic/abilities/score-input-01.json
```

### 截图清单

- [ ] 正常诊断输出截图（含子分数 + 证据引用）
- [ ] 降级模式截图（标注 degraded）
- [ ] Schema 校验通过截图

---

## WF-03：JD 要求级匹配

### 平台配置

| 配置项 | 值 |
|--------|-----|
| 任务名称 | `career-coach-WF-03-jd-match` |
| 触发条件 | 用户上传 JD 文件或粘贴 JD 文本 |
| 输入变量 | `resume_clean_text`（来自 WF-01）、`jd_text`（用户输入） |
| 输出变量 | `match_result_json`（逐条 requirement 的四态匹配结果） |

### 搭建步骤

1. **创建对话任务**，命名为 `career-coach-WF-03-jd-match`
2. **配置工具调用链**：

```
步骤1: python tools/match_requirements.py --resume {{resume_clean_text}} --job {{jd_text}} --backend bm25 --output /tmp/match_result.json
步骤2: 解析 /tmp/match_result.json，提取四态统计
步骤3: 展示匹配结果（covered/weak/missing/unknown 分布）
```

3. **配置 Embedding 后端（可选）**：设置环境变量后可用 `--backend embedding`
4. **配置模型路由**：任务类型 `jd_match_explain`，temperature=0.3，max_tokens=2048，timeout=20s
5. **配置降级路径**：embedding 不可用 -> BM25 降级，UI 标注"简化匹配"

### 验收命令

```bash
python tools/match_requirements.py --resume tests/fixtures-synthetic/resumes/resume-01-swe.txt --job tests/fixtures-synthetic/jobs/job-01-swe.txt --backend bm25 --output /tmp/wf03_match.json
python -c "
import json
r = json.load(open('/tmp/wf03_match.json'))
assert 'requirements' in r
states = {x['status'] for x in r['requirements']}
assert states <= {'covered','weak','missing','unknown'}
print('WF-03 match test passed:', len(r['requirements']), 'requirements')
"
python -m pytest tests/test_match.py -v
```

### 截图清单

- [ ] JD 匹配结果截图（四态分布饼图/列表）
- [ ] BM25 降级标注"简化匹配"截图
- [ ] 匹配明细（covered/weak/missing 逐条展示）截图

---

## WF-04：模拟面试

### 平台配置

| 配置项 | 值 |
|--------|-----|
| 任务名称 | `career-coach-WF-04-interview` |
| 触发条件 | WF-03 完成后，用户选择"开始模拟面试" |
| 输入变量 | `job_profile`（来自 WF-03）、`resume_profile`（来自 WF-02）、`match_gaps`（来自 WF-03） |
| 输出变量 | `interview_report_json`（面试评分 + 逐轮记录） |

### 搭建步骤

1. **创建对话任务**，命名为 `career-coach-WF-04-interview`
2. **配置面试引擎**：

```
步骤1: from interview_engine import InterviewEngine
步骤2: engine = InterviewEngine(model_router=<router>)
步骤3: session = engine.start(job_profile, resume_profile, match_gaps)
步骤4: 循环: q = engine.next_question(session) -> 展示问题 -> 用户回答 -> engine.submit_answer(session, answer)
步骤5: report = engine.end_session(session) -> 输出评分报告
```

3. **配置模型路由**：任务类型 `interview_question`（temperature=0.4）和 `interview_review`（temperature=0.3）
4. **配置降级路径**：模型不可用 -> 题库模板降级
5. **配置语音增强**（可选）：接入 voice_handler + voice.js

### 验收命令

```bash
python -m pytest tests/test_e2e.py::TestWF04Interview -v
python -c "
import sys; sys.path.insert(0, 'tools')
from interview_engine import InterviewEngine
engine = InterviewEngine(model_router=None)
session = engine.start(
    {'title':'test','requirements':[{'id':'J1','type':'hard','text':'Python'}]},
    {'score_R':70}, [{'id':'J1','type':'hard','text':'Python','status':'weak'}]
)
q = engine.next_question(session)
assert q['question'] is not None
r = engine.submit_answer(session, '我用Python开发了一个数据分析平台，日处理100万条记录，性能提升40%。')
report = engine.end_session(session)
assert 'score_I' in report
print('WF-04 interview test passed, score_I:', report['score_I'])
"
```

### 截图清单

- [ ] 面试问题展示截图
- [ ] 用户回答 + 追问截图
- [ ] 面试评分报告截图（含 score_I + 逐轮子分）
- [ ] 降级模式截图（题库模板问题）

---

## WF-05：能力评分与七天计划

### 平台配置

| 配置项 | 值 |
|--------|-----|
| 任务名称 | `career-coach-WF-05-ability` |
| 触发条件 | WF-02 + WF-03 + WF-04 均完成 |
| 输入变量 | `score_R`、`score_M`、`score_I`（来自前序 WF） |
| 输出变量 | `C0`（综合基线）、`C7_low`/`C7_high`（七天情景推演）、`seven_day_plan` |

### 搭建步骤

1. **创建对话任务**，命名为 `career-coach-WF-05-ability`
2. **配置复算**：

```
步骤1: 构造 score-input JSON（包含 R/M/I 子分数）
步骤2: python tools/rescore.py --input /tmp/score_input.json --output /tmp/score_result.json
步骤3: 解析 C0, C7_low, C7_high
```

3. **配置七天计划生成**：任务类型 `seven_day_plan`，temperature=0.2，max_tokens=2048，timeout=20s
4. **配置降级路径**：模型不可用 -> 使用 DEGRADED_OUTPUTS["seven_day_plan"] 骨架

### 验收命令

```bash
python -m pytest tests/test_e2e.py::TestWF05Rescore -v
python -c "
import sys, json; sys.path.insert(0, 'tools')
import rescore
si = json.load(open('tests/fixtures-synthetic/abilities/score-input-01.json'))
r = rescore.compute(si)
assert 0 <= r['C0'] <= 100
assert r['C7_low'] <= r['C7_high']
print('WF-05 rescore test passed, C0:', r['C0'])
"
```

### 截图清单

- [ ] 综合评分展示截图（R/M/I/C0）
- [ ] 七天情景推演截图（C7_low ~ C7_high）
- [ ] 七天提升计划截图

---

## WF-06：数据生命周期管理

### 平台配置

| 配置项 | 值 |
|--------|-----|
| 任务名称 | `career-coach-WF-06-ops` |
| 触发条件 | 用户请求删除数据 / 系统定时清理 / 合规审计 |
| 输入变量 | `user_id` |
| 输出变量 | `lifecycle_status`（active/deleted）、`consent_status` |

### 搭建步骤

1. **创建对话任务**，命名为 `career-coach-WF-06-ops`
2. **配置生命周期管理**：

```
步骤1: from privacy_lifecycle import DataLifecycle, ConsentManager, PIIScanner
步骤2: dl = DataLifecycle(store_dir="/tmp/career_coach_data")
步骤3: 根据用户操作:
       - 查看状态: dl.is_active(user_id) / dl.is_deleted(user_id)
       - 删除数据: dl.delete(user_id)
       - 验证可调用模型: dl.assert_can_call_model(user_id)
步骤4: PIIScanner.scan_logs() 定期扫描日志残留
```

3. **配置同意管理**：grant_consent / revoke_consent / check_consent
4. **配置降级路径**：assert_can_call_model 失败 -> 阻断模型调用，提示用户重新授权

### 验收命令

```bash
python -m pytest tests/test_e2e.py::TestWF06Privacy -v
python -c "
import sys; sys.path.insert(0, 'tools')
from privacy_lifecycle import DataLifecycle, ConsentManager
import tempfile, os
d = tempfile.mkdtemp()
dl = DataLifecycle(store_dir=d)
dl.activate('test_user')
assert dl.is_active('test_user')
dl.assert_can_call_model('test_user')
dl.delete('test_user')
assert dl.is_deleted('test_user')
try:
    dl.assert_can_call_model('test_user')
    assert False, 'should raise PermissionError'
except PermissionError:
    pass
print('WF-06 privacy lifecycle test passed')
"
```

### 截图清单

- [ ] 数据状态查看截图（active/deleted）
- [ ] 删除数据操作截图
- [ ] 删除后模型调用阻断截图
- [ ] PII 日志扫描结果截图

---

## 搭建后验收总表

| 工作流 | 验收命令 | 预期结果 | 截图数 | 状态 |
|--------|----------|----------|--------|------|
| WF-01 | `pytest tests/test_extract.py tests/test_deidentify.py -v` | 全部通过 | 5 | [ ] |
| WF-02 | `pytest tests/test_e2e.py::TestModelRouterDegradation -v` | 降级测试通过 | 3 | [ ] |
| WF-03 | `pytest tests/test_match.py -v` | 四态匹配通过 | 3 | [ ] |
| WF-04 | `pytest tests/test_e2e.py::TestWF04Interview -v` | 面试流程通过 | 4 | [ ] |
| WF-05 | `pytest tests/test_e2e.py::TestWF05Rescore -v` | 复算通过 | 3 | [ ] |
| WF-06 | `pytest tests/test_e2e.py::TestWF06Privacy -v` | 隐私生命周期通过 | 4 | [ ] |

## 常见问题

**Q: DuMate 平台不支持 Python 脚本直接调用怎么办？**
A: 将工具调用封装为 DuMate 平台的自定义 Skill，通过 Skill 入口触发工具链。

**Q: 模型 API 不可用时如何验证工作流？**
A: 所有工作流已内置降级路径（DEGRADED_OUTPUTS），降级输出标注 `degraded=true`，可正常走通流程。

**Q: Embedding 后端如何切换？**
A: 设置环境变量 `ZHIPU_API_KEY`（智谱AI免费2000万Token），运行 `python tools/match_requirements.py --backend embedding`。详见 `docs/embedding-migration-guide.md`。
