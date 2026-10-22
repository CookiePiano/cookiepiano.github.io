"""Site identity shared by the builder, publisher, and tests.

Authorization uses immutable GitHub IDs so an account or repository rename
cannot silently disable or widen the publishing gate.
"""

SITE_URL = 'https://cookiepiano.github.io/'
OWNER_ID = '220297881'
PUBLIC_REPOSITORY_ID = '1375398745'
CONTENT_REPOSITORY_NAME = 'pistco-site-content'
LANGUAGES = ('ko', 'en')

# Fixed public entrypoints copied from docs/ (generated pages are added per language).
STATIC_FILES = ('index.html', '404.html', '.nojekyll', 'assets/styles.css', 'assets/theme.js', 'assets/icon.svg', 'admin/index.html')
PUBLIC_FILES = frozenset(STATIC_FILES) | {lang + '/index.html' for lang in LANGUAGES}
