# PISTCO Research Portfolio

Bilingual static portfolio at https://cookiepiano.github.io/, published from main:/docs. Browser code uses no server, database, or framework.

The owning GitHub account was renamed from PISTCO to CookiePiano (owner ID 220297881), and this repository from pistco.github.io to cookiepiano.github.io. The site brand remains PISTCO. Never link to github.com/PISTCO: the retired name can be claimed by another account.

## Management and authoritative inputs

- Management entrance: https://cookiepiano.github.io/admin/
- Private drafts: https://github.com/CookiePiano/pistco-site-content (owner only).
- Content source: content/profile.json, content/projects.json, and referenced media/ files in the private repository.
- Layout source: templates/page.html (one template for both languages), templates/ui.json (Korean and English interface copy with identical keys), docs/assets/styles.css, docs/assets/icon.svg, and docs/admin/index.html.
- Site identity: scripts/site_config.py holds the site URL, owner ID, public repository ID, and the public file allowlist shared by the builder, publisher, and tests.
- Generated pages: docs/ko/index.html, docs/en/index.html, and docs/assets/media/.
- Public entrypoints: docs/index.html (browser-language redirect, Korean fallback), docs/404.html, and docs/.nojekyll.

The public management page contains navigation links only. GitHub enforces access to actual editing, uploads, previews, and manual publishing. Do not enter passwords or tokens into the website.

## Design

The page is drawn as a research record on graph paper: the hero is a drawing sheet whose title block (name, status, summary, document type) sits in the lower-right corner, as on an engineering drawing. Dark mode follows the system setting and renders as a cyanotype blueprint. Typography uses IBM Plex Sans KR (400/500/700) from Google Fonts with system Korean fallbacks. Numbering appears only where order is real: project order and management steps.

## Local workspace

Initial location: C:\Users\razer\Desktop\project\github_pages. Private source belongs under .private/site-content/, excluded from public Git tracking. The isolated build environment is .private/build-venv/. No system packages are changed.

Use that environment's Python interpreter with scripts/build.py, passing --content .private/site-content --out .private/preview-NEW-NAME. The output directory must not exist. Open generated ko/index.html or en/index.html locally. The existing node scripts/preview.mjs command serves the public docs/ directory on loopback port 4173 only.

Build requirements: Python 3.12+ and requirements-build.txt (Pillow 12.3.0). Run scripts/test_security.py for regression checks. Edit private content or public templates, never generated page content. Pull the public repository after workflow publication before further local changes. Preserve unrelated edits.

## Owner workflow

1. Open the management page and sign in to GitHub as CookiePiano.
2. Edit both translations in the private JSON files. Upload images to media/ and reference a path such as media/project.jpg.
3. Run Preview private draft on main. Download its private preview artifact and open ko/index.html or en/index.html locally. Artifacts expire after 3 days.
4. Run Publish approved draft on main with its confirmation checked. This publishes the whole current draft snapshot.
5. Review the summary: private source commit, engine commit, public commit, and public HTTP verification.

Saving drafts never publishes. Unreferenced images stay private. Removing references removes files from the next live snapshot, but previously published material can remain in public Git history, caches, and visitor copies.

## Validation and security boundary

- Validate strict schema, both languages, unique IDs/order, HTTPS links, and file references before output.
- Escape all content as text; reject non-HTTPS links, embedded credentials, whitespace and backslashes in URLs. Content is substituted once, so placeholder syntax inside content is never expanded.
- Allow JPEG/PNG/WebP up to 10 MiB and 25 megapixels; reject animation, mismatched formats, corrupt files, symlinks and path traversal.
- Decode/re-encode to WebP, at most 2400 pixels per side, without original EXIF/XMP metadata. Public filenames are content hashes.
- Export fixed entrypoints and explicitly referenced normalized images only. Never copy the private source tree or Git history.
- Preserve non-site public files. Publish through one non-force ref update; concurrent writes fail rather than overwrite newer work.
- Identity checks use immutable IDs, so a future rename neither disables nor widens publishing. Private workflow jobs require repository owner ID and actor ID 220297881, a triggering actor equal to the repository owner, the pistco-site-content repository name, workflow_dispatch, and main. Publishing additionally requires a checked confirmation. The publisher addresses the public repository by ID (1375398745). No external PR trigger is configured.

## Publishing App

Create a dedicated GitHub App installed only on CookiePiano/cookiepiano.github.io with Contents read/write and required Metadata read. Disable webhooks; grant no other repository, organization, account, or Actions-write permissions. Installations follow repositories through renames.

Set APP_CLIENT_ID as a variable and APP_PRIVATE_KEY as an Actions Secret in the private repository. Never commit the key or paste it into the public site. The workflow requests a short-lived token for only the public repository and contents:write, then revokes it on completion. Until configured, publishing fails closed; preview works without it.

All Actions and the public engine are pinned to reviewed commit SHAs in both private workflows. Update engine pins deliberately when changing rendering/security code.

## Recovery and limits

Restore an earlier private content version, preview, then publish again. Do not force-push or represent rollback as erasing public history. If Pages verification times out after a public commit was created, inspect that deployment before retrying.

Private Actions use account-included usage. This project does not enable paid usage. Quota/permission failure leaves the existing site available.

## Verification record

Initial portfolio was deployed and verified on 2026-09-18 KST. Public collaborator listing confirmed only the owner before this change. Tests do not guarantee absolute security, and giving another user access changes the trust boundary.

2026-10-22 KST: redesign, single-template refactor, and rename to cookiepiano.github.io. 18 local regression tests passed; local pages were checked in light and dark modes at desktop and 375 px widths. Remote results are recorded in the private README.
