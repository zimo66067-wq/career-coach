#!/usr/bin/env python3
"""
Push local commits to GitHub via REST API, bypassing schannel TLS issues.
Usage: python push-via-api.py <repo_owner> <repo_name> <branch_name> <token>
"""
import sys, subprocess, json, base64, time, os

REPO_OWNER = sys.argv[1] if len(sys.argv) > 1 else "zimo66067-wq"
REPO_NAME  = sys.argv[2] if len(sys.argv) > 2 else "career-coach"
BRANCH     = sys.argv[3] if len(sys.argv) > 3 else "main"
TOKEN      = sys.argv[4] if len(sys.argv) > 4 else os.environ.get("GITHUB_TOKEN", "")
BASE_URL   = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"

def git_cmd(cmd):
    full = f"git {cmd}"
    r = subprocess.run(full, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[GIT ERROR] {full}\n{r.stderr}", file=sys.stderr)
        sys.exit(1)
    return r.stdout.strip()

def git_cmd_bytes(cmd):
    """Run git command and return raw bytes (for binary blobs)."""
    full = f"git {cmd}"
    r = subprocess.run(full, shell=True, capture_output=True)
    if r.returncode != 0:
        print(f"[GIT ERROR] {full}\n{r.stderr.decode(errors='replace')}", file=sys.stderr)
        sys.exit(1)
    return r.stdout

def github_post(endpoint, payload, method="POST"):
    import urllib.request, urllib.error
    url = f"{BASE_URL}/{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"[API ERROR] {method} {url} -> {e.code}\n{body}", file=sys.stderr)
        # Return None on 422 (object may already exist) to let caller decide
        if e.code == 422:
            return None
        raise

def github_get(endpoint):
    import urllib.request
    url = f"{BASE_URL}/{endpoint}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

# ------------------------------------------------------------------
# 1. Resolve local HEAD and remote ref
# ------------------------------------------------------------------
local_head = git_cmd("rev-parse HEAD")
remote_ref = github_get(f"git/refs/heads/{BRANCH}")
remote_sha = remote_ref["object"]["sha"] if remote_ref else None

print(f"Local HEAD:  {local_head}")
print(f"Remote {BRANCH}: {remote_sha}")

if local_head == remote_sha:
    print("Already up to date.")
    sys.exit(0)

# ------------------------------------------------------------------
# 2. Collect missing objects (commits, trees, blobs)
# ------------------------------------------------------------------
print("\n[1/4] Collecting objects to upload...")

# Traverse from local HEAD backwards, collecting all commits until
# we hit a commit already known to GitHub (common ancestor or root)
commit_list = []
current = local_head
visited_commits = set()

while current and current not in visited_commits:
    visited_commits.add(current)
    # Check if this commit already exists on GitHub
    exists = github_get(f"git/commits/{current}")
    if exists:
        print(f"  Found existing commit on GitHub: {current[:12]}")
        break
    commit_list.append(current)
    # Get parent
    parents = []
    commit_info = git_cmd(f"cat-file -p {current}")
    for line in commit_info.splitlines():
        if line.startswith("parent "):
            parents.append(line.split()[1])
    if parents:
        current = parents[0]  # Follow first parent (mainline)
    else:
        current = None

commit_list.reverse()  # Oldest first
print(f"  New commits to push: {len(commit_list)}")

# Collect all trees and blobs referenced by these new commits
# Note: do NOT include remote_sha - it may not exist locally
trees_to_upload = set()
blobs_to_upload = set()

for commit_sha in commit_list:
    commit_info = git_cmd(f"cat-file -p {commit_sha}")
    tree_sha = None
    for line in commit_info.splitlines():
        if line.startswith("tree "):
            tree_sha = line.split()[1]
            break
    if tree_sha:
        trees_to_upload.add(tree_sha)

visited_trees = set()
while trees_to_upload:
    tree_sha = trees_to_upload.pop()
    if tree_sha in visited_trees:
        continue
    visited_trees.add(tree_sha)
    
    tree_data = git_cmd(f"cat-file -p {tree_sha}").splitlines()
    for line in tree_data:
        parts = line.split()
        if len(parts) >= 4:
            mode = parts[0]
            obj_type = parts[1]
            obj_sha = parts[2]
            if obj_type == "blob":
                blobs_to_upload.add(obj_sha)
            elif obj_type == "tree":
                trees_to_upload.add(obj_sha)

print(f"  Trees to upload:  {len(visited_trees)}")
print(f"  Blobs to upload:  {len(blobs_to_upload)}")

# ------------------------------------------------------------------
# 3. Upload blobs
# ------------------------------------------------------------------
print("\n[2/4] Uploading blobs...")

blobs_uploaded = 0
blobs_skipped = 0

for blob_sha in list(blobs_to_upload):
    # Check if blob already exists on GitHub
    exists = github_get(f"git/blobs/{blob_sha}")
    if exists:
        blobs_skipped += 1
        continue
    
    # Get blob content (binary-safe)
    content = git_cmd_bytes(f"cat-file -p {blob_sha}")
    encoded = base64.b64encode(content).decode("ascii")
    
    # GitHub API has 100MB limit for blobs via API
    if len(encoded) > 100 * 1024 * 1024:
        print(f"  [SKIP] Blob {blob_sha} too large for API upload")
        continue
    
    result = github_post("git/blobs", {"content": encoded, "encoding": "base64"})
    if result and result.get("sha") == blob_sha:
        blobs_uploaded += 1
    else:
        # If sha mismatch, GitHub computed different sha (likely due to encoding differences)
        # This is okay for our purposes since we'll use GitHub's returned sha in trees
        blobs_uploaded += 1

print(f"  Blobs uploaded: {blobs_uploaded}, skipped: {blobs_skipped}")

# ------------------------------------------------------------------
# 4. Upload trees
# ------------------------------------------------------------------
print("\n[3/4] Uploading trees...")

# Sort trees by dependency (leaf trees first)
# We need to build a dependency graph
tree_deps = {}
for tree_sha in visited_trees:
    deps = set()
    tree_data = git_cmd(f"cat-file -p {tree_sha}").splitlines()
    for line in tree_data:
        parts = line.split()
        if len(parts) >= 4 and parts[1] == "tree":
            deps.add(parts[2])
    tree_deps[tree_sha] = deps

# Topological sort
tree_order = []
remaining = set(visited_trees)
while remaining:
    found = False
    for tree_sha in list(remaining):
        if tree_deps[tree_sha].issubset(set(tree_order)):
            tree_order.append(tree_sha)
            remaining.remove(tree_sha)
            found = True
            break
    if not found:
        # Cycle shouldn't happen in git trees, but handle gracefully
        tree_order.extend(list(remaining))
        remaining.clear()

trees_uploaded = 0
trees_skipped = 0
tree_sha_map = {}  # local_sha -> github_sha (in case of mismatch)

for tree_sha in tree_order:
    # Check if tree already exists on GitHub
    exists = github_get(f"git/trees/{tree_sha}")
    if exists:
        trees_skipped += 1
        tree_sha_map[tree_sha] = tree_sha
        continue
    
    # Build tree entries
    entries = []
    tree_data = git_cmd(f"cat-file -p {tree_sha}").splitlines()
    for line in tree_data:
        parts = line.split(maxsplit=3)
        if len(parts) >= 4:
            mode = parts[0]
            obj_type = parts[1]
            obj_sha = parts[2]
            path = parts[3]
            
            entry = {
                "path": path,
                "mode": mode,
                "type": obj_type,
                "sha": tree_sha_map.get(obj_sha, obj_sha)
            }
            entries.append(entry)
    
    result = github_post("git/trees", {"tree": entries})
    if result:
        returned_sha = result.get("sha")
        tree_sha_map[tree_sha] = returned_sha
        if returned_sha == tree_sha:
            trees_uploaded += 1
        else:
            # SHA mismatch - GitHub computed different sha
            trees_uploaded += 1
    else:
        # 422 might mean tree already exists
        trees_skipped += 1
        tree_sha_map[tree_sha] = tree_sha

print(f"  Trees uploaded: {trees_uploaded}, skipped: {trees_skipped}")

# ------------------------------------------------------------------
# 5. Upload commits
# ------------------------------------------------------------------
print("\n[4/4] Uploading commits...")

# Process commits in chronological order (oldest first)
commit_order = list(reversed(commit_list))
commits_uploaded = 0
commits_skipped = 0
commit_sha_map = {}

for commit_sha in commit_order:
    # Check if commit already exists on GitHub
    exists = github_get(f"git/commits/{commit_sha}")
    if exists:
        commits_skipped += 1
        commit_sha_map[commit_sha] = commit_sha
        continue
    
    # Parse commit
    commit_raw = git_cmd(f"cat-file -p {commit_sha}")
    lines = commit_raw.splitlines()
    
    tree_sha = None
    parents = []
    author_name = author_email = author_date = None
    committer_name = committer_email = committer_date = None
    message_lines = []
    in_message = False
    
    for line in lines:
        if in_message:
            message_lines.append(line)
        elif line.startswith("tree "):
            tree_sha = line.split()[1]
        elif line.startswith("parent "):
            parents.append(line.split()[1])
        elif line.startswith("author "):
            parts = line[7:].rsplit(" ", 2)
            author_name_email = parts[0]
            author_date = " ".join(parts[1:])
            # Parse name <email>
            lt = author_name_email.rfind("<")
            gt = author_name_email.rfind(">")
            if lt > 0 and gt > lt:
                author_name = author_name_email[:lt].strip()
                author_email = author_name_email[lt+1:gt]
        elif line.startswith("committer "):
            parts = line[10:].rsplit(" ", 2)
            committer_name_email = parts[0]
            committer_date = " ".join(parts[1:])
            lt = committer_name_email.rfind("<")
            gt = committer_name_email.rfind(">")
            if lt > 0 and gt > lt:
                committer_name = committer_name_email[:lt].strip()
                committer_email = committer_name_email[lt+1:gt]
        elif line == "":
            in_message = True
    
    # Use mapped tree sha
    mapped_tree = tree_sha_map.get(tree_sha, tree_sha)
    
    # Use mapped parent shas
    mapped_parents = [commit_sha_map.get(p, p) for p in parents]
    
    payload = {
        "message": "\n".join(message_lines),
        "tree": mapped_tree,
        "parents": mapped_parents
    }
    
    if author_name and author_email:
        payload["author"] = {"name": author_name, "email": author_email, "date": author_date}
    if committer_name and committer_email:
        payload["committer"] = {"name": committer_name, "email": committer_email, "date": committer_date}
    
    result = github_post("git/commits", payload)
    if result:
        returned_sha = result.get("sha")
        commit_sha_map[commit_sha] = returned_sha
        commits_uploaded += 1
    else:
        commits_skipped += 1
        commit_sha_map[commit_sha] = commit_sha

print(f"  Commits uploaded: {commits_uploaded}, skipped: {commits_skipped}")

# ------------------------------------------------------------------
# 6. Update ref
# ------------------------------------------------------------------
print(f"\n[UPDATE] Setting refs/heads/{BRANCH} -> {commit_sha_map[local_head]}")

result = github_post(f"git/refs/heads/{BRANCH}", {
    "sha": commit_sha_map[local_head],
    "force": True
}, method="PATCH")

if result:
    print(f"\n[SUCCESS] Pushed {local_head} to {BRANCH}")
    print(f"  Commit: {commit_sha_map[local_head]}")
    sys.exit(0)
else:
    print("\n[FAILED] Could not update ref", file=sys.stderr)
    sys.exit(1)
