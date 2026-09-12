# Phase 1 — Repository Audit

Repository: `fasalsaiko-sudo/Muhammed-Fasal`
Audited commit: `1efab73` ("Deploy cybersecurity portfolio") — the current `main` and the deployed product.
Method: every number below comes from a command run against the working tree (`git ls-tree`, `grep -o`, `md5sum`, `gh api`). Commands are listed in §9 so any claim can be re-checked.

---

## 1. Existing pages

63 tracked files. 6 HTML documents:

| Page | Size | Role | Status |
|---|---|---|---|
| `index.html` | 19,955 B / 110 lines | Single-page portfolio (hero, about, experience, skills, projects, research, certifications, education, resume, contact) | **The product** |
| `game.html` | 5,191 B / 111 lines | Cybersecurity quiz arena + AI chat widget + results dashboard | Live |
| `hacker-room.html` | 2,071 B / 47 lines | Three.js 3D room with monitor shortcuts | Live |
| `profile.html` | 391 B / 1 line | Meta-refresh redirect → `index.html#about` | Redirect stub |
| `writeups.html` | 416 B / 1 line | Meta-refresh redirect → `index.html#projects` | Redirect stub |
| `blog/index.html` | 568 B / 18 lines | Placeholder "Security Blog" page | Placeholder |

`README.md` is a single line (`# portfolio`). `blog/README.md` and `components/README.md` are notes-only.

---

## 2. Existing functional features (verified as wired)

**`index.html` → `assets/js/portfolio.js` (117 lines), styles `assets/css/portfolio.css` + `polish.css`:**

- Dark/light theme toggle with `localStorage` persistence (`mf-theme`), pre-paint inline script to avoid flash
- Mobile nav toggle + `aria-expanded` state
- Scroll progress bar, sticky header shadow, back-to-top
- `IntersectionObserver` reveal animations (3 observers), timeline draw-in
- Active-nav highlighting by section
- Project category filtering (5 buttons: All / VAPT / Security tools / Labs / Other)
- Project case-study dialogs — 5 `<template>` blocks rendered into a `<dialog>` via `showModal()`
- Certificate dialogs — 4 cards open the certificate image in a `<dialog>`
- Dynamic footer year
- Accessibility: skip link, `.sr-only`, `prefers-reduced-motion` blocks in **both** CSS files, semantic sections

**`game.html` / `hacker-room.html` → `assets/js/main.js` (406 lines) + `game.js` / `hacker-room.js`:**
`main.js` runs 12 initialisers on `DOMContentLoaded`: `initNav`, `initReveal`, `initTyping`, `initCounters`, `initCursor`, `initTilt`, `initProjectFilters`, `initModal`, `initChatbot`, `initThreeScene`, `initTheme`, `initPageTransitions`.
- Quiz: question bank by difficulty, timer, progress bar, localStorage leaderboard, results dashboard
- AI chat widget: the **live** one is `initChatbot()` in `main.js` against the `.chatbot` markup in `game.html`
- Hacker room: Three.js canvas (`#hacker-room-canvas`)

External CDN dependencies (only these three): GSAP 3.12.5, GSAP ScrollTrigger 3.12.5, three.js r134 — all on cdnjs, all `defer`red, all with non-CDN fallbacks in `main.js` (`initReveal` falls back to `IntersectionObserver` when GSAP is absent).

---

## 3. Orphaned JS/CSS modules — **not live features**

These files are tracked but **loaded by no page**, and the DOM ids they query **exist in no HTML file**. They are inert code, not working features:

| Module | Referenced by | Required DOM ids | Ids present? |
|---|---|---|---|
| `assets/js/ai-assistant.js` (+`ai-assistant.css`) | nothing | `ai-toggle, ai-window, ai-close, ai-form, ai-input, ai-messages` | ✗ none |
| `assets/js/soc-dashboard.js` (+css) | nothing | `threat-feed, soc-active-threats, soc-blocked-attacks, soc-countries-count, soc-risk-level` | ✗ none |
| `assets/js/threatmap.js` (+css) | nothing | `globe, threat-map, active-attacks, total-attacks, top-country, threat-map-fallback` | ✗ none |
| `assets/js/network-graph.js` (+css) | nothing | `network-canvas, network-graph, network-tooltip` | ✗ none |
| `assets/js/terminal.js` | nothing | `terminal, terminal-input, terminal-nav-output` | ✗ none |
| `assets/js/bugbounty-dashboard.js` (+css) | nothing | `bounty-activity-log` | ✗ none |
| `assets/js/hacker-typing.js` (+`hacker-terminal.css`) | nothing | `hacker-terminal, terminal-output` | ✗ none |

**Consequence for the plan:** the spec's "preserve SOC dashboard / threat map / network graph / terminal / bug bounty dashboard" cannot mean "keep them working" — they have never run on the deployed site. They are latent components. Recommended treatment: leave the files untouched in Phase 2–10, and decide separately whether to (a) delete, (b) wire up as opt-in sections, or (c) keep as-is. **No decision is taken in this phase.**

CSS loaded by exactly one page: `assets/css/style.css` (game, hacker-room, blog), `assets/css/hacker-room.css` (hacker-room). `assets/css/portfolio.css` + `polish.css` (index).

---

## 4. Duplicate assets

12 md5 collisions — every file at the repository root is a byte-identical copy of one under `assets/images/`:

| Root copy (unreferenced) | Canonical copy |
|---|---|
| `hero1.jpg` | `assets/images/hero.jpg` |
| `azure-ai.jpg` | `assets/images/certs/azure-ai.jpg` |
| `cisco-ccst.jpg` | `assets/images/certs/cisco-ccst.jpg` |
| `junior-pt.jpg` | `assets/images/certs/junior-pt.jpg` |
| `intrella-internship.jpg` | `assets/images/certs/intrella-internship.jpg` |
| `magic-bus.jpg` | `assets/images/certs/magic-bus.jpg` |
| `game/images-1..6.jpg` (6 files) | `assets/images/game/images-1..6.jpg` |

`game.html` references `assets/images/game/images-2.jpg`; nothing references the root `game/` directory or the root `*.jpg` files.

Unused-but-tracked assets (no HTML reference): `assets/images/hero11.jpg`, `assets/images/hero22.jpg`, `assets/images/certs/intrella-internship.jpg`, `assets/images/certs/magic-bus.jpg` (the last two are real certificates that the static page never renders — they must survive migration).

Legacy stubs: `js/main.js` (103 B) and `js/game.js` (58 B) are comment-only redirects kept for old bookmarks. `css/style.css` (12.9 KB) begins with `@import url('../assets/css/style.css')` and then defines a **second, conflicting** design system (`--background-color: #111`, `--accent-color: #407000`). It is loaded by no page.

---

## 5. Hardcoded portfolio content (the migration surface)

All content lives in `index.html` markup:

| Content | Count in HTML | Destination |
|---|---|---|
| Project cards | 6 | `projects` |
| Case-study dialog bodies (`<template id=…>`) | 5 (`hospital`, `websafe`, `privesc`, `browser`, `weather`) | `projects.description/problem/solution/methodology/findings_summary` |
| Certificate cards | 4 rendered (+2 unreferenced images) | `certifications` + `certification_media` |
| Experience entries | 3 | `experience` |
| Skill category cards | 3 | `skill_categories` |
| Skill list items | 23 `<li>` | `skills` |
| Social links | 3 (LinkedIn, GitHub, Bugcrowd) | `social_links` |
| Tool strip items | 7 | `skills` (Tools) or site settings |
| Filter buttons | 5 | derived from `projects.category` |
| Education entry | 1 (BCA, University of Mysore, 2022–2025) | `experience` or profile long-bio |
| JSON-LD Person schema | 1 block | `profile` + `social_links` (regenerated) |

Hardcoded identifiers that must become configuration, not literals:

- Contact email `fasalmuhammed7025@gmail.com` — 2 occurrences (contact section + mailto)
- Resume Google Drive file id `1r_GAL74ZHspFKN3NY7adFykLIlX2IynN` — 2 occurrences (view + download link)
- GitHub `Fasal17`, LinkedIn `muhammed-fasal-ms`, Bugcrowd `h/Fasal17`
- Hero image path `assets/images/muhammed-fasal-hero.png` (also in `og:image`)
- `<title>`, meta description, OG title/description, `theme-color #0b1220`

No secrets are present in the repository (no tokens, keys or credentials found in tracked files).

---

## 6. GitHub Pages deployment structure — verified via the API

```
GET /repos/fasalsaiko-sudo/Muhammed-Fasal/pages
  status      : "built"
  html_url    : https://fasalsaiko-sudo.github.io/Muhammed-Fasal/
  build_type  : "legacy"          ← Jekyll, not Actions
  source      : { branch: "main", path: "/" }
  cname       : null
  https_enforced : true
```

Implications:

1. **The published site is the repository root of `main`.** Any file committed to `main` is a candidate for publication.
2. **`build_type: legacy` means Jekyll processes the tree.** Jekyll copies non-HTML files through to `_site`, so committing `backend/`, `admin/`, `docs/`, `.env.example` or `database/` to `main` **would publish Python source, Dart source and configuration templates on the public internet**. `backend/.env.example` contains no real secrets, but publishing infrastructure layout and env-var names is exactly what a security portfolio should not do.
3. There is **no `.nojekyll`**, no `_config.yml`, no `CNAME`, no `.github/workflows/`.
4. The site is served under a **project path** (`/Muhammed-Fasal/`), so all asset URLs must stay relative. `index.html` already complies.

**Decision required before any code is pushed to `main`** (three options, my recommendation first):

- **(A) Add `_config.yml` with an `exclude:` list** for `backend`, `admin`, `docs`, `database`, `scripts`, `.github`, `requirements.txt`, `*.md` except README. Keeps `build_type: legacy` and `path: /` exactly as they are — zero risk to the live site, one small new file.
- (B) Switch Pages to a GitHub Actions workflow that publishes an explicit frontend subset. Cleaner long-term, but it changes the deployment mechanism of a working site.
- (C) Move the public site into `frontend/` and repoint Pages. Highest risk; explicitly discouraged by the brief ("adapt the structure rather than blindly moving everything").

Until this decision is made, **nothing new is committed to `main`.** Work stays on the branch.

---

## 7. Migration risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Jekyll publishing `backend/`, `admin/`, `.env.example` on the public site | **High** | Option (A) above, applied in the same PR as the first commit to `main` |
| R2 | Breaking the 5 project dialogs / 4 certificate dialogs by replacing markup with API-rendered DOM | **High** | Frontend hydration must reuse the existing `<template>` + `<dialog>` mechanism, not replace it |
| R3 | Losing the 2 certificates that exist as images but are never rendered (`intrella-internship`, `magic-bus`) | Medium | Imported as `DRAFT` certifications; verified present in seed |
| R4 | Resume link breakage during CV migration (2 hardcoded Drive URLs) | Medium | `GET /api/cv` seeded from the same Drive id `1r_GAL74…`; static links stay until the API path is verified |
| R5 | Deleting the root-level duplicate images that some external link or bookmark may reference | Medium | Nothing is deleted before Phase 9 verification |
| R6 | CDN failure (GSAP / three.js) | Low | Fallbacks already exist in `main.js`; unchanged |
| R7 | Orphan modules mistakenly "wired up" and changing page behaviour | Low | Orphans stay untouched; explicit decision deferred |
| R8 | SQLite passing tests that PostgreSQL would fail (timezone, JSON, enum CHECK) | Medium | Both are run; see the note in §8 and Phase 3 |
| R9 | Google Drive not reachable without a service account | Medium | Storage abstraction with an explicit health status; documented, not faked |
| R10 | Repo has no `.gitignore` at all | Medium | One is added before any new files are committed |

---

## 8. Files that must remain untouched

**Never modified, moved, renamed or deleted by the CMS work:**

```
index.html                     # content becomes API-hydrated, structure preserved
game.html                      hacker-room.html
profile.html                   writeups.html
blog/index.html                blog/README.md        components/README.md
assets/css/portfolio.css       assets/css/polish.css     assets/css/style.css
assets/css/hacker-room.css     assets/css/ai-assistant.css   assets/css/bugbounty-dashboard.css
assets/css/hacker-terminal.css assets/css/network-graph.css  assets/css/soc-dashboard.css
assets/css/threatmap.css
assets/js/portfolio.js         assets/js/main.js     assets/js/game.js
assets/js/hacker-room.js       assets/js/ai-assistant.js     assets/js/bugbounty-dashboard.js
assets/js/hacker-typing.js     assets/js/network-graph.js    assets/js/soc-dashboard.js
assets/js/terminal.js          assets/js/threatmap.js
assets/images/**               game/*.jpg            favicon.svg    robots.txt
css/style.css                  js/main.js            js/game.js
```

**Modified only additively** (existing markup/behaviour preserved, new hooks added):

```
index.html    # + <script src="assets/js/api.js"> and data-* hydration hooks
README.md     # currently one line; rewritten in a later phase
```

**New files only** (never overwriting anything above):

```
backend/  admin/  database/  docs/  scripts/  data/portfolio.json  .github/workflows/  .gitignore
```

---

## 9. Verification commands

```bash
git ls-tree -r --name-only HEAD                       # 63 tracked files
gh api repos/fasalsaiko-sudo/Muhammed-Fasal/pages     # build_type legacy, branch main, path /
grep -oE '(href|src)="[^"]+"' *.html blog/*.html      # per-page asset wiring
grep -oE "getElementById\('[^']+'\)" assets/js/*.js   # orphan DOM-id check
md5sum $(git ls-tree -r --name-only HEAD | grep -E '\.(jpg|png|svg)$') | sort
grep -o 'class="project-card' index.html | wc -l      # and the other content counters
```

---

## 10. Current state of already-written code (disclosure)

Before this phase boundary was set, a backend tree was generated in one pass. It exists on the branch as **untracked** files and is **not** committed:

```
?? backend/    ?? database/    ?? scripts/
```

Status of that code, stated plainly:

- The app boots: 68 OpenAPI paths / 84 operations; Alembic migration `9b1e48f41e7e` created 21 tables on a real PostgreSQL 18 engine; the seed script populated 6 projects, 6 certifications, 24 skills, 3 experience entries, 3 social links, 1 CV version; public endpoints returned the migrated content over HTTP.
- The test suite was **65 passed / 16 failed** at the point work stopped. The failures cluster in OAuth callback tests, CV/media upload tests and two validators.
- Therefore, against the phase plan: **Phase 2 is not yet passing and is not claimed as complete.**

Treatment going forward: this code is **input to Phase 2, not output of it**. Phase 2 will reduce the backend to the foundation scope you listed, get its tests green, and only then proceed. Nothing above is deleted.
