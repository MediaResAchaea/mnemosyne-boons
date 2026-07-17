#!/bin/sh
# Re-export data.js from the Mudlet db, commit, and push (Pages redeploys on push).
set -e
cd "$(dirname "$0")"
python3 export_site.py "$@"
git add data.js
if git diff --cached --quiet; then
  echo "no data changes to publish"
else
  git commit -m "data: refresh boon database ($(date +%Y-%m-%d))"
  git push
  echo "pushed -- site updates in a minute or two"
fi
