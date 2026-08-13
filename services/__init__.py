# -*- coding: utf-8 -*-
"""职业教练 services 层（阶段5）。

api/index.py 仅保留参数校验与路由转发；业务编排收敛到本包：
- diagnosis_service：F1 简历诊断（模型/规则降级）
- match_service：F2 JD 解析与匹配
- interview_service：F3 面试会话 + F4 能力报告
- task_service：F2 分片任务推进
- apply_service：F5 投递闭环（求职信 + 申请跟踪）
"""
