# Changelog

格式遵循 Keep a Changelog；每次冻结记一条。commit hash 在实际提交后回填。

## [Unreleased]

### Frozen - 基线冻结（commit B）
- docs/PRD.md、architecture.md、privacy.md 首版冻结
- contracts/ 四个 JSON Schema + scoring.md（R/M/I/C0/C7 公式与手算示例）冻结
- tests/fixtures-synthetic 合成样本集（简历×5、JD×4、面试×1、能力×2）
- workflows/ WF-01~06 占位定义
- handoffs/001-product-to-build.md

### Added - 前端原型与提示词（commit C）
- ui/prototype 五页面 × 五状态静态原型（ECharts 雷达三级降级）
- prompts/ 七份提示词模块（含事实锁与注入防御）
- docs/demo-script.md
- handoffs/002-frontend-to-pipeline.md

### Added - 工具链与测试（commit D）
- tools/ 八个工具：extract_text / deidentify / validate_schema / rescore / log_sanitize / match_requirements / radar_adapter / redflag
- tests/ pytest 契约测试 + 故障注入 + 验收与彩排清单

### Added - 审查与交接（commit E）
- docs/review.md（一审结构合规 + 二审跨文件一致性）
- handoffs/003-tools-to-dumate.md（交 DuMate 主交接文件）
