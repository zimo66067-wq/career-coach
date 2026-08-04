#!/usr/bin/env python3
"""
Push local git commits to GitHub via REST API (bypass schannel TLS timeout).
Usage: python push-via-api-v2.py <owner> <repo> <branch> <token>
"""
import sys, subprocess, json, base64, urllib.request, urllib.error, os

OWNER = sys.argv[1] if len(sys.argv) > 1 else "zimo66067-wq"
REPO  = sys.argv[2] if len(sys.argv) > 2 else "career-coach"
BRANCH= sys.argv[3] if len(sys.argv) > 3 else "main"
TOKEN = sys.argv[4] if len(sys.argv) > 4 else os.environ.get("GITHUB_TOKEN", "")
BASE  = f"https://api.github.com/repos/{OWNER}/{REPO}"

def gitcmd(cmd, allow_fail=False):
    r = subprocess.run(f"git {cmd}", shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        if allow_fail:
            return None
        print(f"[GIT ERR] git {cmd}\n{r.stderr}", file=sys.stderr)
        sys.exit(1)
    return r.stdout.strip()

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
    except Exception as e:
        print(f"[NET ERR] {method} {url}: {e}", file=sys.stderr)
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

# ------------------------------------------------------------------
# 1. HEAD & remote state
# ------------------------------------------------------------------
local_head = gitcmd("rev-parse HEAD")
remote_ref = api_get(f"git/refs/heads/{BRANCH}")
remote_sha = remote_ref["object"]["sha"] if remote_ref else None
print(f"Local HEAD : {local_head}")
print(f"Remote main: {remote_sha}")

if local_head == remote_sha:
    print("Already up to date.")
    sys.exit(0)

# ------------------------------------------------------------------
# 2. Collect commits to push (walk back from HEAD)
# ------------------------------------------------------------------
print("\n[1/4] Collecting commits...")
commits_to_push = []
c = local_head
while True:
    if c == remote_sha:
        break
    commits_to_push.append(c)
    parents = []
    for line in gitcmd(f"cat-file -p {c}").splitlines():
        if line.startswith("parent "):
            parents.append(line.split()[1])
    if not parents:
        break
    c = parents[0]

commits_to_push.reverse()  # oldest first
print(f"  Commits: {len(commits_to_push)}")
if not commits_to_push:
    print("Nothing to push.")
    sys.exit(0)

# Save remote_sha for tree/blobs collection (may exist on GitHub only)
remote_only_sha = remote_sha
remote_sha_for_range = remote_sha

# ------------------------------------------------------------------
# 3. Collect trees & blobs
# ------------------------------------------------------------------
print("[2/4] Collecting trees & blobs...")
trees = set()
blobs = set()
for sha in commits_to_push:
    for line in gitcmd(f"cat-file -p {sha}").splitlines():
        if line.startswith("tree "):
            trees.add(line.split()[1])
            break

stack = list(trees)
visited_trees = set()
while stack:
    t = stack.pop()
    if t in visited_trees:
        continue
    visited_trees.add(t)
    for line in gitcmd(f"cat-file -p {t}").splitlines():
        parts = line.split()
        if len(parts) >= 4:
            typ = parts[1]
            sha = parts[2]
            if typ == "blob":
                blobs.add(sha)
            elif typ == "tree":
                stack.append(sha)

print(f"  Trees : {len(visited_trees)}")
print(f"  Blobs : {len(blobs)}")

# ------------------------------------------------------------------
# 4. Upload blobs (skip if exists)
# ------------------------------------------------------------------
print("[3/4] Uploading blobs...")
blobs_ok = 0
blobs_skip = 0
for sha in blobs:
    if api_get(f"git/blobs/{sha}"):
        blobs_skip += 1
        continue
    content = gitcmd(f"cat-file -p {sha}")
    enc = base64.b64encode(content.encode()).decode()
    r = api("POST", "git/blobs", {"content": enc, "encoding": "base64"})
    if r:
        blobs_ok += 1
    else:
        print(f"  [WARN] blob {sha} upload returned 422, may already exist")
        blobs_skip += 1

print(f"  Uploaded: {blobs_ok}, Skipped: {blobs_skip}")

# ------------------------------------------------------------------
# 5. Upload trees (leaf-first dependency order)
# ------------------------------------------------------------------
print("[4/4] Uploading trees...")
# Build dependency graph
leaf_first = []
remaining = set(visited_trees)
tree_deps = {t: set() for t in visited_trees}
for t in visited_trees:
    for line in gitcmd(f"cat-file -p {t}").splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] == "tree":
            child = parts[2]
            if child in visited_trees:
                tree_deps[t].add(child)

while remaining:
    ready = {t for t in remaining if tree_deps[t].issubset(set(leaf_first))}
    if not ready:
        leaf_first.extend(remaining)
        break
    leaf_first.extend(ready)
    remaining -= ready

trees_ok = 0
trees_skip = 0
sha_map = {}
for t in leaf_first:
    if api_get(f"git/trees/{t}"):
        trees_skip += 1
        sha_map[t] = t
        continue
    entries = []
    for line in gitcmd(f"cat-file -p {t}").splitlines():
        parts = line.split(maxsplit=3)
        if len(parts) >= 4:
            entries.append({
                "path": parts[3],
                "mode": parts[0],
                "type": parts[1],
                "sha": sha_map.get(parts[2], parts[2])
            })
    r = api("POST", "git/trees", {"tree": entries})
    if r:
        sha_map[t] = r.get("sha", t)
        trees_ok += 1
    else:
        trees_skip += 1
        sha_map[t] = t

print(f"  Uploaded: {trees_ok}, Skipped: {trees_skip}")

# ------------------------------------------------------------------
# 6. Upload commits
# ------------------------------------------------------------------
print("[5/4] Uploading commits...")
commit_map = {}
for sha in commits_to_push:
    lines = gitcmd(f"cat-file -p {sha}").splitlines()
    tree_sha = None
    parents = []
    author = committer = None
    msg = []
    phase = "header"
    for line in lines:
        if phase == "header":
            if line.startswith("tree "):
                tree_sha = line.split()[1]
            elif line.startswith("parent "):
                parents.append(line.split()[1])
            elif line.startswith("author "):
                author = line[7:]
            elif line.startswith("committer "):
                committer = line[10:]
            elif line == "":
                phase = "msg"
        else:
            msg.append(line)

    def parse_person(s):
        lt, gt = s.rfind("<"), s.rfind(">")
        if lt > 0 and gt > lt:
            name = s[:lt].strip()
            email = s[lt+1:gt]
            date = s[gt+1:].strip()
            return {"name": name, "email": email, "date": date}
        return None

    payload = {
        "message": "\n".join(msg),
        "tree": sha_map.get(tree_sha, tree_sha),
        "parents": [commit_map.get(p, p) for p in parents]
    }
    if author:
        payload["author"] = parse_person(author)
    if committer:
        payload["committer"] = parse_person(committer)

    r = api("POST", "git/commits", payload)
    if r:
        commit_map[sha] = r.get("sha", sha)
        print(f"  {sha[:12]} -> {commit_map[sha][:12]}")
    else:
        commit_map[sha] = sha
        print(f"  {sha[:12]} (skipped, may exist)")

# ------------------------------------------------------------------
# 7. Update ref
# ------------------------------------------------------------------
print(f"\n[UPDATE] refs/heads/{BRANCH} -> {commit_map[local_head][:12]}")
final_sha = commit_map[local_head]
r = api("PATCH", f"git/refs/heads/{BRANCH}", {"sha": final_sha, "force": True})
if r:
    print(f"\n[SUCCESS] Pushed to {BRANCH}")
    print(f"  Commit: {final_sha}")
    sys.exit(0)
else:
    # Fallback: try POST if ref doesn't exist, or force=true PATCH
    print("\n[RETRY] Force-pushing with force=true...")
    r = api("PATCH", f"git/refs/heads/{BRANCH}", {"sha": final_sha, "force": True})
    if r:
        print(f"\n[SUCCESS] Pushed to {BRANCH}")
        print(f"  Commit: {final_sha}")
        sys.exit(0)
    print("[FAILED] Could not update ref", file=sys.stderr)
    sys.exit(1)
