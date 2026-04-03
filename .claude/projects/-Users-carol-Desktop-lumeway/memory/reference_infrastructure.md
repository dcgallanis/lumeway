---
name: Lumeway infrastructure references
description: Key infrastructure details - Railway, database, admin, blog pipeline, analytics
type: reference
---

- **Hosting**: Railway (auto-deploys from GitHub main branch)
- **Database**: PostgreSQL on Railway (subscribers table), SQLite fallback locally
- **Admin dashboard**: lumeway.co/admin (protected by ADMIN_KEY env var in Railway)
- **Blog pipeline**: cowork saves HTML to ~/Desktop/lumeway-cowork/blog/ → sync-blog.sh copies to repo → push to main → live
- **Blog auto-sync**: macOS launchd job (co.lumeway.sync-blog) runs weekdays at 9 AM
- **Analytics**: Google Analytics GA4, measurement ID G-QHWJDRDR9R
- **Pinterest verification**: meta tag on all pages
- **Search Console**: sitemap at lumeway.co/sitemap.xml (dynamic, auto-includes blog posts)
