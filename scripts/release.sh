#!/usr/bin/env bash
# AutoAgent release helper — create a SemVer git tag and push.
#
# Usage:
#   ./scripts/release.sh patch   # 1.0.0 → 1.0.1
#   ./scripts/release.sh minor   # 1.0.0 → 1.1.0
#   ./scripts/release.sh major   # 1.0.0 → 2.0.0

set -euo pipefail

cd "$(dirname "$0")/.."

bump="${1:-patch}"
current=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")
current="${current#v}"

IFS='.' read -r major minor patch <<< "$current"
major="${major:-0}"; minor="${minor:-0}"; patch="${patch:-0}"

case "$bump" in
  major) major=$((major + 1)); minor=0; patch=0 ;;
  minor) minor=$((minor + 1)); patch=0 ;;
  patch) patch=$((patch + 1)) ;;
  *)
    echo "usage: $0 {major|minor|patch}"
    exit 1
    ;;
esac

new_tag="v${major}.${minor}.${patch}"

echo "Current: v${current} → New: ${new_tag}"
echo ""
echo "Recent commits since last tag:"
git log --oneline "v${current}..HEAD" 2>/dev/null || git log --oneline -10

echo ""
read -rp "Create and push tag ${new_tag}? [y/N] " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
  echo "aborted"
  exit 0
fi

git tag -a "$new_tag" -m "AutoAgent ${new_tag}"
git push origin "$new_tag"
echo "tag ${new_tag} pushed"
