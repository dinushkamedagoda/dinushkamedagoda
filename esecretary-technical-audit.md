# eSecretary.lk — Technical Audit & Competitive Review

**Date:** 2 July 2026
**Scope:** https://esecretary.lk/ — technical health, SEO, and competitive position in the Sri Lankan company registration / secretarial services market.

> **Method note:** This audit was compiled from search-engine index data, third-party site analyzers (Accessify), and Similarweb traffic data. Live page-level inspection was not possible from this environment, so figures like page weight and request counts come from the most recent third-party crawl and should be re-verified with Google PageSpeed Insights before acting.

---

## 1. Site profile

- **Platform:** Hand-built static HTML site (pages like `contact.html`, `company-registration-in-sri-lanka.html`, `index-si.html`). No CMS detected.
- **Languages:** English + Sinhala, implemented as parallel static pages (`-si.html` suffix).
- **Homepage title:** *"Online Company Registration In Sri Lanka | Company Secretary | eSecretary"* — good keyword targeting.
- **Services indexed:** company incorporation (LKR 20,000; LKR 30,000 priority incl. free TIN registration, share certificates, 1-year retainer), guarantee-limited companies/associations, trademark registration, annual returns. Service brochures published as PDFs.

## 2. Technical issues found

### Performance (highest-impact fixes)
| Issue | Detail | Fix |
|---|---|---|
| No GZIP/Brotli compression on HTML | ~83% of HTML transfer size (≈62.6 kB) wasted | Enable compression at the web server / put Cloudflare (free tier) in front |
| HTML not minified | ≈15.4 kB (20%) savings available | Minify as part of a build/deploy step |
| Too many requests | ~55 requests to render homepage; **13 separate CSS files** and **10 separate JS files** | Bundle to 1–2 files each; remove unused libraries |
| Heavy page | ~1.2 MB total, ~595 kB images — heavier than the top 1M websites benchmark | Convert images to WebP/AVIF, resize to display dimensions, lazy-load below-the-fold images |
| No CDN/caching evidence | Sri Lankan-hosted static assets served without edge caching | Cloudflare free plan gives CDN + compression + HTTP/2/3 in one step |

Positives: images individually compressed, CSS/JS files are minified, UTF-8 declared correctly.

### SEO / discoverability
1. **No Open Graph description** (confirmed by crawler) — links shared on Facebook/WhatsApp/LinkedIn render poorly. Add full OG + Twitter Card tags on every page. This matters a lot in Sri Lanka where discovery is heavily Facebook/WhatsApp-driven.
2. **No hreflang between English and Sinhala pages** (parallel `-si.html` files with no signaled relationship) — Google can treat them as unrelated/duplicate pages and may show the wrong language to users. Add `<link rel="alternate" hreflang="si" ...>` / `hreflang="en"` pairs.
3. **Sinhala text encoding defect in titles:** indexed titles show `ශ්රී` instead of `ශ්‍රී` (missing zero-width joiner), so "Sri Lanka" renders wrong in Sinhala SERP titles. Audit all Sinhala copy for ZWJ issues.
4. **Legacy `.html` URLs** (`company-registration-in-sri-lanka.html`) — functional but dated; if ever restructured, use clean URLs with 301 redirects. Low priority.
5. **No structured data** — add `LocalBusiness`/`ProfessionalService`, `Service` with price, and `FAQPage` JSON-LD. Competitors mostly lack this too, so it's a cheap win for rich results.
6. **Thin content:** the "blog" is a single static page (`company-registration-in-sri-lanka-blog.html`). Competitors that outrank you for registration keywords (Simplebooks, Bizadvisor, Counselit) win on deep guide content.
7. **Verify basics:** `sitemap.xml`, `robots.txt`, Google Search Console + Business Profile registration, canonical tags — could not be confirmed remotely; check each.

### Trust & conversion
- No visible online sign-up/lead-capture flow — competitors (Simplebooks, Beehoney) offer full online registration dashboards; eSecretary's path is phone/email.
- Add a WhatsApp click-to-chat CTA, Google reviews embed, and clear package comparison table (your LKR 20k/30k pricing is genuinely competitive — Counselit starts at LKR 24,990 — but it's buried).
- Bounce rate 54.2% with only 1.76 pages/visit suggests visitors land, read one page, and leave without converting.

## 3. Competitive position

| Site | Monthly visits* | SL country rank | Notes |
|---|---|---|---|
| **simplebooks.com** | ~48,500 | #2,438 | Market leader: online dashboard, 8,000+ clients, 4.95★, deep content hub, name-check tool |
| **esecretary.lk** | ~1,100 | #25,047 | ~2% of Simplebooks' traffic |
| Others (ECSS, Beehoney, Bizadvisor, ASAC/anandasirisena.lk, NYX, incorp.lk, Counselit) | niche | — | Compete on content depth (Bizadvisor handbook, Counselit fee guides) or online flows (Beehoney) |

\* Similarweb, most recent published figures.

**Where you stand in search:** eSecretary ranks **#1** for "company secretary services Sri Lanka" and around **#7** for "company registration in Sri Lanka online" in the (US-index) results checked — genuinely strong for a static site, driven by good title tags and an exact-match domain. But rankings alone aren't converting into traffic: ~1.1K visits/month vs 48.5K for Simplebooks. The gap is **content volume, online product experience, and brand/review presence**, not on-page keywords.

## 4. Prioritised action plan

**Week 1 (near-zero cost, big impact)**
1. Put the site behind Cloudflare free tier → compression, CDN, HTTP/2, TLS hardening in one move.
2. Add Open Graph + Twitter Card meta to every page.
3. Add hreflang pairs between English/Sinhala pages; fix Sinhala ZWJ encoding.
4. Bundle CSS (13→1) and JS (10→1); convert hero/service images to WebP.

**Month 1**
5. Add JSON-LD structured data (LocalBusiness, Service with pricing, FAQPage).
6. Set up/verify Google Search Console, sitemap.xml, and a fully-populated Google Business Profile with review collection.
7. Add WhatsApp CTA + a simple online enquiry/order form to cut the phone-call friction.

**Quarter 1**
8. Build a real content hub: 10–15 in-depth guides (eROC walkthrough, Form 1/18/19 explained, director requirements, annual return deadlines, tax registration) in **both English and Sinhala** — Sinhala long-form content is an underserved niche none of the major competitors cover well.
9. Add a free company-name-check tool (Simplebooks' biggest organic magnet).
10. Consider migrating the hand-edited HTML to a static site generator (Astro/Hugo/11ty) so minification, bundling, sitemaps and hreflang are automatic.

## 5. Bottom line

The site's fundamentals (keyword-targeted titles, exact-match domain, competitive pricing) have earned first-page rankings for core secretarial keywords, but the site is technically dated — uncompressed, heavy, 55-request static pages with no social/structured metadata — and offers no online conversion path. You sit in the mid-tier of a market Simplebooks dominates ~40:1 on traffic. The Week-1 fixes above are cheap and mechanical; the strategic gap to close is content depth and an online sign-up experience.
