#!/usr/bin/env bash
# Push local HEAD to GitHub via REST API (bypass schannel TLS timeout)
# Usage: ./push-head-api.sh [owner] [repo] [branch] [token]
set -euo pipefail

OWNER="${1:-zimo66067-wq}"
REPO="${2:-career-coach}"
BRANCH="${3:-main}"
TOKEN="${4:-${GITHUB_TOKEN:-}}"
BASE="https://api.github.com/repos/${OWNER}/${REPO}"

api() {
    local method="$1" endpoint="$2"
    local data="${3:-}"
    if [[ -n "$data" ]]; then
        curl -s -X "$method" -H "Authorization: token ${TOKEN}" \
            -H "Accept: application/vnd.github.v3+json" \
            -H "Content-Type: application/json" \
            -d "$data" "${BASE}/${endpoint}"
    else
        curl -s -X "$method" -H "Authorization: token ${TOKEN}" \
            -H "Accept: application/vnd.github.v3+json" \
            "${BASE}/${endpoint}"
    fi
}

api_get() {
    curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: token ${TOKEN}" \
        -H "Accept: application/vnd.github.v3+json" \
        "${BASE}/$1" 2>/dev/null
}

# 1. Get local HEAD and remote ref
LOCAL_HEAD=$(git rev-parse HEAD)
REMOTE_SHA=$(api "GET" "git/refs/heads/${BRANCH}" | python3 -c "import sys,json; print(json.load(sys.stdin)['object']['sha'])")

echo "Local HEAD : ${LOCAL_HEAD}"
echo "Remote ${BRANCH}: ${REMOTE_SHA}"

if [[ "$LOCAL_HEAD" == "$REMOTE_SHA" ]]; then
    echo "Already up to date."
    exit 0
fi

# 2. Collect all trees and blobs
ROOT_TREE=$(git log --format='%T' -1 HEAD)
echo ""
echo "[1/4] Collecting objects from HEAD tree..."

declare -A TREES=()
declare -A BLOBS=()

collect_tree() {
    local t="$1"
    if [[ -n "${TREES[$t]:-}" ]]; then return; fi
    TREES[$t]=1
    while IFS='' read -r line; do
        read -r mode typ sha path <<< "$line"
        if [[ "$typ" == "blob" ]]; then
            BLOBS[$sha]=1
        elif [[ "$typ" == "tree" ]]; then
            collect_tree "$sha"
        fi
    done < <(git cat-file -p "$t")
}

collect_tree "$ROOT_TREE"
echo "  Trees: ${#TREES[@]}, Blobs: ${#BLOBS[@]}"

# 3. Upload blobs
echo "[2/4] Uploading blobs..."
BLOB_COUNT=0
BLOB_SKIP=0

for sha in "${!BLOBS[@]}"; do
    code=$(api_get "git/blobs/${sha}")
    if [[ "$code" == "200" ]]; then
        ((BLOB_SKIP++))
        continue
    fi
    # Read binary blob and base64 encode via temp file to avoid pipe encoding issues
    tmpfile=$(mktemp)
    git cat-file -p "$sha" > "$tmpfile"
    enc=$(python3 -c "import base64; print(base64.b64encode(open('$tmpfile', 'rb').read()).decode())")
    rm -f "$tmpfile"
    api "POST" "git/blobs" "{\"content\":\"${enc}\",\"encoding\":\"base64\"}" > /dev/null
    ((BLOB_COUNT++))
done

echo "  Uploaded: ${BLOB_COUNT}, Skipped: ${BLOB_SKIP}"

# 4. Upload trees (deepest first)
echo "[3/4] Uploading trees..."

# Calculate depth for each tree
declare -A DEPTH=()

calc_depth() {
    local t="$1" d="${2:-0}"
    if [[ -n "${DEPTH[$t]:-}" && ${DEPTH[$t]} -ge $d ]]; then return; fi
    DEPTH[$t]=$d
    while IFS='' read -r line; do
        read -r mode typ sha path <<< "$line"
        if [[ "$typ" == "tree" && -n "${TREES[$sha]:-}" ]]; then
            calc_depth "$sha" $((d+1))
        fi
    done < <(git cat-file -p "$t")
}

calc_depth "$ROOT_TREE"

# Sort trees by depth (deepest first)
mapfile -d '' SORTED_TREES < <(printf '%s\0' "${!TREES[@]}" | sort -z -t\0 -k1,1 -n < <(for t in "${!TREES[@]}"; do echo "${DEPTH[$t]} $t"; done | sort -rn | awk '{print $2}'))

# Actually just use bash sort
declare -a TREE_LIST=()
for t in "${!TREES[@]}"; do
    TREE_LIST+=("$t")
done

# Bubble sort by depth (deepest first)
for ((i=0; i<${#TREE_LIST[@]}; i++)); do
    for ((j=i+1; j<${#TREE_LIST[@]}; j++)); do
        if [[ ${DEPTH[${TREE_LIST[$i]}]} -lt ${DEPTH[${TREE_LIST[$j]}]} ]]; then
            tmp="${TREE_LIST[$i]}"
            TREE_LIST[$i]="${TREE_LIST[$j]}"
            TREE_LIST[$j]="$tmp"
        fi
    done
done

declare -A GH_TREE_MAP=()
TREE_COUNT=0
TREE_SKIP=0

for t in "${TREE_LIST[@]}"; do
    code=$(api_get "git/trees/${t}")
    if [[ "$code" == "200" ]]; then
        GH_TREE_MAP[$t]="$t"
        ((TREE_SKIP++))
        continue
    fi
    
    # Build entries array
    entries="["
    first=true
    while IFS='' read -r line; do
        read -r mode typ sha path <<< "$line"
        mapped_sha="${GH_TREE_MAP[$sha]:-$sha}"
        if [[ "$first" == "true" ]]; then
            first=false
        else
            entries+=","
        fi
        entries+="{\"path\":\"$path\",\"mode\":\"$mode\",\"type\":\"$typ\",\"sha\":\"$mapped_sha\"}"
    done < <(git cat-file -p "$t")
    entries+="]"
    
    resp=$(api "POST" "git/trees" "{\"tree\":$entries}")
    new_sha=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('sha',''))")
    if [[ -n "$new_sha" ]]; then
        GH_TREE_MAP[$t]="$new_sha"
        ((TREE_COUNT++))
    else
        echo "  [WARN] Tree $t upload failed"
        GH_TREE_MAP[$t]="$t"
    fi
done

echo "  Uploaded: ${TREE_COUNT}, Skipped: ${TREE_SKIP}"

# 5. Create commit
echo "[4/4] Creating commit..."

# Extract commit message and author info
commit_raw=$(git cat-file -p HEAD)
author_line=$(echo "$commit_raw" | grep "^author " | head -1)
committer_line=$(echo "$commit_raw" | grep "^committer " | head -1)

# Parse message (after blank line)
message=$(echo "$commit_raw" | sed '0,/^$/d')

# Parse author
author_name=$(echo "$author_line" | sed 's/^author //' | sed 's/ <.*$//')
author_email=$(echo "$author_line" | grep -o '<[^>]*>' | tr -d '<>')
author_date=$(echo "$author_line" | sed 's/^.*> //')

committer_name=$(echo "$committer_line" | sed 's/^committer //' | sed 's/ <.*$//')
committer_email=$(echo "$committer_line" | grep -o '<[^>]*>' | tr -d '<>')
committer_date=$(echo "$committer_line" | sed 's/^.*> //')

# Escape message for JSON
json_msg=$(echo "$message" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')

commit_payload=$(cat <<EOF
{
  "message": ${json_msg},
  "tree": "${GH_TREE_MAP[$ROOT_TREE]}",
  "parents": ["${REMOTE_SHA}"],
  "author": {"name": "${author_name}", "email": "${author_email}", "date": "${author_date}"},
  "committer": {"name": "${committer_name}", "email": "${committer_email}", "date": "${committer_date}"}
}
EOF
)

resp=$(api "POST" "git/commits" "$commit_payload")
new_sha=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('sha',''))")

if [[ -z "$new_sha" ]]; then
    echo "[FAILED] Could not create commit"
    echo "$resp"
    exit 1
fi

echo "  Created: ${new_sha}"

# 6. Update ref
echo ""
echo "[UPDATE] refs/heads/${BRANCH} -> ${new_sha:0:12}"
resp=$(api "PATCH" "git/refs/heads/${BRANCH}" "{\"sha\":\"${new_sha}\",\"force\":true}")
ref_sha=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin).get('object',{}).get('sha',''))")

if [[ -n "$ref_sha" ]]; then
    echo ""
    echo "[SUCCESS] Pushed to ${BRANCH}"
    echo "  Commit: ${new_sha}"
    echo "  Parent: ${REMOTE_SHA}"
else
    echo "[FAILED] Could not update ref"
    echo "$resp"
    exit 1
fi
