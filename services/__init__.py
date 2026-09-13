# -*- coding: utf-8 -*-
"""职业教练 services 层（阶段5）。

api/index.py 仅保留参数校验与路由转发；业务编排收敛到本包：
- diagnosis_service：简历诊断（模型/规则降级）
- match_service：目标岗位 JD 解析与匹配
- interview_service：面试会话 + 能力报告
- apply_service：投递闭环（求职信 + 申请跟踪）
- organization_service：单位/职位索引契约（阶段1：未配置即显式降级）
"""
