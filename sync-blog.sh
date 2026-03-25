#!/bin/bash
# Sync blog posts from lumeway-cowork/blog/ into the site repo
# Usage: ./sync-blog.sh
# Copies post.html files from cowork blog folders into blog-posts/
# Then commits and pushes so Railway auto-deploys

COWORK_BLOG="/Users/carol/Desktop/lumeway-cowork/blog"
SITE_BLOG="$(dirname "$0")/blog-posts"

mkdir -p "$SITE_BLOG"

count=0
for dir in "$COWORK_BLOG"/*/; do
  [ -d "$dir" ] || continue
  slug=$(basename "$dir")
  # Skip non-post directories
  [ "$slug" = "published" ] && continue
  [ -f "$dir/post.html" ] || continue

  # Copy if new or updated
  if [ ! -f "$SITE_BLOG/$slug.html" ] || [ "$dir/post.html" -nt "$SITE_BLOG/$slug.html" ]; then
    cp "$dir/post.html" "$SITE_BLOG/$slug.html"
    echo "Synced: $slug"
    count=$((count + 1))
  fi
done

if [ "$count" -eq 0 ]; then
  echo "No new posts to sync."
  exit 0
fi

echo ""
echo "$count post(s) synced to blog-posts/"
echo ""
echo "To deploy, run:"
echo "  git add blog-posts/ && git commit -m 'Add new blog posts' && git push"
