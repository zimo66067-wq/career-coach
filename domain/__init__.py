# -*- coding: utf-8 -*-
"""domain · 职业教练的领域层（纯逻辑，不依赖数据库、Flask 或 provider）

分层方向（见 docs/domain-model.md）：Routes → Services → **Domain** → Repositories / Providers。
本包只放"什么算合法"的规则，不做 I/O：

- ``evidence``        CareerEvidence：个人职业事实的唯一可信来源
- ``career_profile``  CareerProfile：证据按六类分支归类
- ``target_job``      TargetJob / JobRequirement / EvidenceMatch / Gap / Decision
- ``interview``       InterviewSession 的子实体与"面试新事实"入口
- ``action``          Gap → Action → Artifact → Outcome 的行动闭环
- ``application``     申请 7 态状态机 + ApplicationOutcome

贯穿全部实体的三条不变量：

1. **任何职业事实都必须能回指来源**：``source_type`` + ``source_quote`` 缺一不可，
   quote 必须是来源原文的逐字子串（与 F1 的 source_span 事实锁同口径）。
2. **AI 不能把推测写成已确认事实**：由模型抽取/推断产生的证据一律以
   ``status='pending'`` 落库，``user_confirmed`` 只能由用户确认置位。
3. **关键判断必须可解释**：TargetJob 的 APPLY / STRETCH / PASS 至少引用 3 条依据。
"""
from domain.errors import DomainError  # noqa: F401

__all__ = ["DomainError"]
