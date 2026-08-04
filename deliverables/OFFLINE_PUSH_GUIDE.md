# 离线推送指南

当前本地领先远程 2 个 commit，沙箱环境 DNS 不可达。

## 方式一：Git Bundle（推荐）

### 当前环境（沙箱）已生成

文件：`deliverables/career-coach-push.bundle`（818KB）

此文件包含 `origin/main..HEAD` 的所有差异，可以安全带走。

### 目标环境（有网络的机器）执行

```bash
# 1. 复制 bundle 到目标机器
scp career-coach-push.bundle user@host:/path/to/

# 2. 进入同一仓库目录
cd career-coach-github

# 3. 确认当前分支是 main，且 origin/main 是最新远程状态
git status
# 应显示：Your branch is behind 'origin/main' by 2 commits

# 4. 从 bundle 提取 commit
git fetch deliverables/career-coach-push.bundle 'refs/*:refs/bundle/*'

# 5. 直接快进合并（无冲突）
git merge refs/bundle/main --ff-only

# 6. 推送到远程
git push origin main
```

如果 `git push` 仍超时，继续用方式二。

---

## 方式二：GitHub API 脚本

### 在目标环境执行

```bash
# 确保在同一仓库目录
cd career-coach-github

# 运行已修复的推送脚本
python scripts/push-via-api.py
```

脚本已修复 binary blob UTF-8 decode 问题，可安全推送 227 个 blob。

---

## 方式三：GitHub Desktop / 其他 Git 客户端

在目标环境用 GitHub Desktop、SourceTree 或其他 Git 客户端打开仓库，直接 push。

---

## 验证推送成功

```bash
git log --oneline origin/main -3
# 应显示：
# 7beb7da p1-p2: degraded screenshots + requirements pin + ...
# bb7b111 p0-all: automation evidence + voice validation + ...
# b591a52 deploy: UI prototype to docs/ for GitHub Pages
```
