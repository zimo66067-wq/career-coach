#!/usr/bin/env python3
"""
Push current HEAD snapshot to GitHub via REST API (bypass schannel TLS timeout).
Usage: python push-head-via-api.py [owner] [repo] [branch] [token]
"""
import sys, subprocess, json, base64, urllib.request, urllib.error, os

OWNER   = sys.argv[1] if len(sys.argv) > 1 else "zimo66067-wq"
REPO    = sys.argv[2] if len(sys.argv) > 2 else "career-coach"
BRANCH  = sys.argv[3] if len(sys.argv) > 3 else "main"
TOKEN   = sys.argv[4] if len(sys.argv) > 4 else os.environ.get("GITHUB_TOKEN", "")
BASE    = f"https://api.github.com/repos/{OWNER}/{REPO}"

def gitcmd_text(cmd):
    r = subprocess.run(f"git {cmd}", shell=True, capture_output=True, text=True)
    return r.stdout.strip(), r.stderr.strip(), r.returncode

def gitcmd_bytes(cmd):
    r = subprocess.run(f"git {cmd}", shell=True, capture_output=True)
    return r.stdout, r.stderr, r.returncode

def api(method, endpoint, payload=None):
    url = f"{BASE}/{endpoint}"
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 422:
            return None
        print(f"[API ERR] {method} {url} -> {e.code}\n{body}", file=sys.stderr)
        raise

def api_get(endpoint):
    url = f"{BASE}/{endpoint}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

# 1. Resolve refs
local_head, _, _ = gitcmd_text("rev-parse HEAD")
remote_ref = api_get(f"git/refs/heads/{BRANCH}")
remote_sha = remote_ref["object"]["sha"] if remote_ref else None

print(f"Local HEAD : {local_head}")
print(f"Remote {BRANCH}: {remote_sha}")

if local_head == remote_sha:
    print("Already up to date.")
    sys.exit(0)

# 2. Collect all trees and blobs from local HEAD tree
print("\n[1/4] Collecting objects from HEAD tree...")
trees = set()
blobs = set()

def collect_tree(tree_sha):
    if tree_sha in trees:
        return
    trees.add(tree_sha)
    out, err, rc = gitcmd_text(f"cat-file -p {tree_sha}")
    if rc != 0:
        print(f"  [WARN] Tree {tree_sha[:12]} missing: {err}")
        return
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            typ = parts[1]
            sha = parts[2]
            if typ == "blob":
                blobs.add(sha)
            elif typ == "tree":
                collect_tree(sha)

root_tree, _, _ = gitcmd_text("log --format=%T -1 HEAD")
collect_tree(root_tree)
print(f"  Trees: {len(trees)}, Blobs: {len(blobs)}")

# 3. Upload blobs (skip if exists, read as binary)
print("[2/4] Uploading blobs...")
blobs_ok = 0
blobs_skip = 0
for sha in blobs:
    if api_get(f"git/blobs/{sha}"):
        blobs_skip += 1
        continue
    content, _, rc = gitcmd_bytes(f"cat-file -p {sha}")
    if rc != 0:
        continue
    enc = base64.b64encode(content).decode()
    api("POST", "git/blobs", {"content": enc, "encoding": "base64"})
    blobs_ok += 1

print(f"  Uploaded: {blobs_ok}, Skipped: {blobs_skip}")

# 4. Upload trees (deepest first, so children are on GitHub before parents)
print("[3/4] Uploading trees...")
tree_depth = {}
def calc_depth(t, d=0):
    if t in tree_depth and tree_depth[t] >= d:
        return
    tree_depth[t] = d
    out, _, rc = gitcmd_text(f"cat-file -p {t}")
    if rc != 0:
        return
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] == "tree":
            calc_depth(parts[2], d + 1)

calc_depth(root_tree)
sorted_trees = sorted(trees, key=lambda t: tree_depth.get(t, 0), reverse=True)

github_tree_map = {}
trees_ok = 0
trees_skip = 0
for t in sorted_trees:
    if api_get(f"git/trees/{t}"):
        github_tree_map[t] = t
        trees_skip += 1
        continue
    entries = []
    out, _, rc = gitcmd_text(f"cat-file -p {t}")
    if rc != 0:
        continue
    for line in out.splitlines():
        parts = line.split(maxsplit=3)
        if len(parts) >= 4:
            mode, typ, sha, path = parts[0], parts[1], parts[2], parts[3]
            entry_sha = github_tree_map.get(sha, sha)
            entries.append({"path": path, "mode": mode, "type": typ, "sha": entry_sha})
    r = api("POST", "git/trees", {"tree": entries})
    if r:
        github_tree_map[t] = r.get("sha", t)
        trees_ok += 1
    else:
        github_tree_map[t] = t

print(f"  Uploaded: {trees_ok}, Skipped: {trees_skip}")

# 5. Parse HEAD commit metadata
print("[4/4] Creating commit...")
commit_raw, _, _ = gitcmd_text("cat-file -p HEAD")
lines = commit_raw.splitlines()
msg = []
author = committer = None
for i, line in enumerate(lines):
    if line.startswith("author "):
        author = line[7:]
    elif line.startswith("committer "):
        committer = line[10:]
    elif line == "":
        msg = lines[i+1:]
        break

def parse_person(s):
    lt, gt = s.rfind("<"), s.rfind(">")
    if lt > 0 and gt > lt:
        return {"name": s[:lt].strip(), "email": s[lt+1:gt], "date": s[gt+1:].strip()}
    return None

payload = {
    "message": "\n".join(msg),
    "tree": github_tree_map.get(root_tree, root_tree),
    "parents": [remote_sha] if remote_sha else []
}
if author:
    payload["author"] = parse_person(author)
if committer:
    payload["committer"] = parse_person(committer)

r = api("POST", "git/commits", payload)
if not r:
    print("[FAILED] Could not create commit", file=sys.stderr)
    sys.exit(1)

new_sha = r["sha"]
print(f"  Created: {new_sha}")

# 6. Update ref
print(f"\n[UPDATE] refs/heads/{BRANCH} -> {new_sha[:12]}")
r = api("PATCH", f"git/refs/heads/{BRANCH}", {"sha": new_sha, "force": True})
if r:
    print(f"\n[SUCCESS] Pushed to {BRANCH}")
    print(f"  Commit: {new_sha}")
    print(f"  Parent: {remote_sha}")
else:
    print("[FAILED] Could not update ref", file=sys.stderr)
    sys.exit(1)
