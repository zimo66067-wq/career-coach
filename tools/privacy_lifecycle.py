# -*- coding: utf-8 -*-
"""privacy_lifecycle.py · 运行态隐私生命周期管理（P1-04）

职责:
  - ConsentManager: 入口同意管理（首次使用必须展示同意条款）
  - DataLifecycle: 数据状态管理（ACTIVE -> DELETED，不可恢复）
  - PIIScanner: 运行后日志扫描（复用 deidentify.scan_residue）
  - 删除后调用检查: DELETED 状态下禁止再调用模型，违则抛 PermissionError

用法:
  from privacy_lifecycle import ConsentManager, DataLifecycle, PIIScanner

  consent = ConsentManager()
  if not consent.check_consent(user_id):
      consent.show_consent(user_id)  # 展示条款，等待用户同意
      consent.grant_consent(user_id)

  lifecycle = DataLifecycle()
  lifecycle.activate(user_id)
  # ... 正常处理 ...
  PIIScanner.scan_logs(log_dir)  # 运行后扫描残留 PII
  lifecycle.delete(user_id)      # 用户发起删除
  # 此后任何模型调用将被拦截
"""
import io
import json
import os
import sys
import time

# 复用 deidentify 的残留扫描能力
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from deidentify import scan_residue
except ImportError:
    scan_residue = None


# =====================================================================
# ConsentManager · 入口同意管理
# =====================================================================

CONSENT_TEXT = """\
【隐私数据处理同意条款】

1. 本系统（Career Coach）将对您上传的简历和岗位描述进行去标识化处理，
   脱除姓名、手机号、邮箱、身份证号等个人身份信息。
2. 去标识化后的文本仅用于简历诊断、岗位匹配和能力评估，不会用于其他用途。
3. 您有权随时删除全部数据，删除后数据不可恢复且不再允许调用模型处理。
4. 系统日志落盘前经过脱敏管道，不含原始 PII。
5. 评分结果是「证据覆盖指数」，不是录用概率。

如同意以上条款，请确认。不同意将无法使用本系统的核心功能。
"""


class ConsentManager:
    """用户同意记录与检查。

    数据模型: {user_id: {consented: bool, timestamp: float, version: str}}
    持久化到 consent_store.json（仅记录同意状态，不含 PII）。
    """

    STORE_FILE = "consent_store.json"
    CONSENT_VERSION = "1.0"

    def __init__(self, store_dir=None):
        self.store_dir = store_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
        self.store_path = os.path.join(self.store_dir, self.STORE_FILE)
        self._store = self._load()

    def _load(self):
        if os.path.exists(self.store_path):
            try:
                with io.open(self.store_path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save(self):
        os.makedirs(self.store_dir, exist_ok=True)
        with io.open(self.store_path, "w", encoding="utf-8") as f:
            json.dump(self._store, f, ensure_ascii=False, indent=2)

    def check_consent(self, user_id):
        """检查用户是否已同意。"""
        record = self._store.get(user_id)
        if not record:
            return False
        return record.get("consented", False) and record.get("version") == self.CONSENT_VERSION

    def show_consent(self, user_id):
        """展示同意条款文本。"""
        print(CONSENT_TEXT)
        return CONSENT_TEXT

    def grant_consent(self, user_id):
        """记录用户同意。"""
        self._store[user_id] = {
            "consented": True,
            "timestamp": time.time(),
            "version": self.CONSENT_VERSION,
        }
        self._save()

    def revoke_consent(self, user_id):
        """撤销用户同意（通常在删除流程中调用）。"""
        if user_id in self._store:
            self._store[user_id]["consented"] = False
            self._save()


# =====================================================================
# DataLifecycle · 数据状态管理
# =====================================================================

class DataLifecycle:
    """用户数据状态机: ACTIVE -> DELETED（不可恢复）。

    状态规则:
      - 新用户 activate 后进入 ACTIVE
      - ACTIVE 状态允许调用模型
      - delete 后进入 DELETED，不可恢复
      - DELETED 状态下任何模型调用抛 PermissionError
    """

    ACTIVE = "ACTIVE"
    DELETED = "DELETED"

    def __init__(self, store_dir=None):
        self.store_dir = store_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
        self.store_path = os.path.join(self.store_dir, "lifecycle_store.json")
        self._states = self._load()

    def _load(self):
        if os.path.exists(self.store_path):
            try:
                with io.open(self.store_path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save(self):
        os.makedirs(self.store_dir, exist_ok=True)
        with io.open(self.store_path, "w", encoding="utf-8") as f:
            json.dump(self._states, f, ensure_ascii=False, indent=2)

    def activate(self, user_id):
        """激活用户数据，进入 ACTIVE 状态。"""
        self._states[user_id] = {
            "status": self.ACTIVE,
            "activated_at": time.time(),
            "deleted_at": None,
        }
        self._save()

    def delete(self, user_id):
        """删除用户数据，进入 DELETED 状态（不可恢复）。"""
        if user_id not in self._states:
            # 未激活的用户直接标记为已删除
            self._states[user_id] = {
                "status": self.DELETED,
                "activated_at": None,
                "deleted_at": time.time(),
            }
        else:
            self._states[user_id]["status"] = self.DELETED
            self._states[user_id]["deleted_at"] = time.time()
        self._save()

    def get_status(self, user_id):
        """获取用户数据状态。"""
        record = self._states.get(user_id)
        if not record:
            return None
        return record.get("status")

    def is_active(self, user_id):
        """检查用户数据是否处于 ACTIVE 状态。"""
        return self.get_status(user_id) == self.ACTIVE

    def is_deleted(self, user_id):
        """检查用户数据是否已删除。"""
        return self.get_status(user_id) == self.DELETED

    def assert_can_call_model(self, user_id):
        """断言用户数据处于可调用模型的状态。

        DELETED 状态下调用此方法将抛出 PermissionError。
        """
        if self.is_deleted(user_id):
            raise PermissionError(
                "用户 %s 的数据已删除（DELETED），禁止再调用模型处理该用户数据" % user_id
            )
        if not self.is_active(user_id):
            raise PermissionError(
                "用户 %s 的数据未激活，无法调用模型" % user_id
            )


# =====================================================================
# PIIScanner · 运行后日志扫描
# =====================================================================

class PIIScanner:
    """运行后日志残留 PII 扫描。

    复用 deidentify.scan_residue 扫描日志文件中的:
      - 手机号
      - 邮箱
      - 身份证号（18位）
    """

    PII_PATTERNS = ["phone", "email", "id"]

    @staticmethod
    def scan_text(text):
        """扫描单段文本中的残留 PII，返回命中列表。"""
        if scan_residue is not None:
            return scan_residue(text)
        # fallback: 基本正则
        import re
        hits = []
        patterns = {
            "phone": re.compile(r"1[3-9]\d{9}"),
            "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
            "id": re.compile(r"\d{17}[\dXx]"),
        }
        for name, pat in patterns.items():
            for m in pat.finditer(text):
                hits.append({"type": name, "value": m.group(0), "pos": m.start()})
        return hits

    @staticmethod
    def scan_file(file_path):
        """扫描单个日志文件，返回命中列表。"""
        try:
            with io.open(file_path, encoding="utf-8") as f:
                content = f.read()
            return PIIScanner.scan_text(content)
        except (IOError, UnicodeDecodeError):
            return []

    @staticmethod
    def scan_logs(log_dir, extensions=None):
        """扫描目录下所有日志文件的残留 PII。

        Args:
            log_dir: 日志目录路径
            extensions: 扫描的文件扩展名列表，默认 [".log", ".txt"]

        Returns:
            dict: {file_path: [pii_hits]}
        """
        if extensions is None:
            extensions = [".log", ".txt"]
        results = {}
        if not os.path.isdir(log_dir):
            return results
        for fname in os.listdir(log_dir):
            if any(fname.endswith(ext) for ext in extensions):
                fpath = os.path.join(log_dir, fname)
                hits = PIIScanner.scan_file(fpath)
                if hits:
                    results[fpath] = hits
        return results

    @staticmethod
    def assert_clean(log_dir):
        """断言日志目录无 PII 残留，有则抛 RuntimeError。"""
        results = PIIScanner.scan_logs(log_dir)
        if results:
            details = []
            for fpath, hits in results.items():
                for h in hits:
                    details.append("%s: %s at %d" % (fpath, h["type"], h["pos"]))
            raise RuntimeError("日志中发现 PII 残留:\n  %s" % "\n  ".join(details))


# =====================================================================
# CLI 入口
# =====================================================================

def main():
    import argparse
    ap = argparse.ArgumentParser(description="隐私生命周期管理工具")
    ap.add_argument("--action", required=True, choices=["consent", "scan", "delete", "status"],
                    help="操作类型")
    ap.add_argument("--user-id", default=None, help="用户 ID（consent/delete/status 需要）")
    ap.add_argument("--log-dir", default=None, help="日志目录（scan 需要）")
    args = ap.parse_args()

    if args.action == "consent":
        if not args.user_id:
            print("需要 --user-id", file=sys.stderr)
            sys.exit(2)
        cm = ConsentManager()
        if cm.check_consent(args.user_id):
            print("用户 %s 已同意（版本 %s）" % (args.user_id, cm.CONSENT_VERSION))
        else:
            cm.show_consent(args.user_id)
            print("\n请使用 grant_consent() 方法记录用户同意")

    elif args.action == "scan":
        if not args.log_dir:
            print("需要 --log-dir", file=sys.stderr)
            sys.exit(2)
        results = PIIScanner.scan_logs(args.log_dir)
        if results:
            print("发现 PII 残留:")
            for fpath, hits in results.items():
                for h in hits:
                    print("  %s: type=%s value=%s pos=%d" % (fpath, h["type"], h["value"], h["pos"]))
            sys.exit(1)
        else:
            print("日志扫描通过，未发现 PII 残留")

    elif args.action == "delete":
        if not args.user_id:
            print("需要 --user-id", file=sys.stderr)
            sys.exit(2)
        dl = DataLifecycle()
        dl.delete(args.user_id)
        cm = ConsentManager()
        cm.revoke_consent(args.user_id)
        print("用户 %s 数据已删除（DELETED，不可恢复），同意已撤销" % args.user_id)

    elif args.action == "status":
        if not args.user_id:
            print("需要 --user-id", file=sys.stderr)
            sys.exit(2)
        dl = DataLifecycle()
        status = dl.get_status(args.user_id)
        cm = ConsentManager()
        consent = cm.check_consent(args.user_id)
        print("用户 %s: 数据状态=%s, 同意=%s" % (
            args.user_id, status or "未初始化", consent))


if __name__ == "__main__":
    main()
