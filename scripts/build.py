"""Build only explicitly referenced public content; never copy the draft tree."""
import argparse
import hashlib
import html
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import warnings
from urllib.parse import urlsplit

from PIL import Image, ImageOps

from site_config import LANGUAGES, SITE_URL, STATIC_FILES

ROOT = Path(__file__).resolve().parents[1]
Image.MAX_IMAGE_PIXELS = 25_000_000
MAX_BYTES = 10 * 1024 * 1024
MAX_SITE_BYTES = 900 * 1024 * 1024
PROFILE_FIELDS = {'title', 'description', 'headline', 'intro', 'footer'}
# Rendered on one line: <title>, <meta> attributes.
SINGLE_LINE_FIELDS = {'title', 'description'}
COMPUTED_FIELDS = {'lang', 'siteUrl', 'name', 'github', 'githubHandle', 'languageNav', 'projectCaption', 'projects', 'featuredRepository'}
PLACEHOLDER = re.compile(r'\{\{(\w+)\}\}')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def keys(value, expected, label):
    require(isinstance(value, dict) and set(value) == set(expected), f'{label}: unexpected or missing fields')


def text(value, label, allow_empty=False):
    require(isinstance(value, str) and len(value) <= 10000, f'{label}: expected text up to 10000 characters')
    require(allow_empty or bool(value.strip()), f'{label}: cannot be empty')
    require(not any(ord(c) < 32 and c not in '\n\t' for c in value), f'{label}: control characters are not allowed')
    return value


def https_url(value):
    text(value, 'URL')
    require(not any(c.isspace() or c == '\\' for c in value), 'URL: invalid characters')
    parsed = urlsplit(value)
    require(parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username and not parsed.password, 'URL: HTTPS without embedded credentials is required')
    return value


def safe_file(base, relative):
    require(isinstance(relative, str) and bool(relative) and '\\' not in relative and ':' not in relative, 'Invalid relative path')
    parts = PurePosixPath(relative)
    require(not parts.is_absolute() and all(p not in ('.', '..') for p in relative.split('/')), 'Path traversal is not allowed')
    target = base
    for part in parts.parts:
        target = target / part
        require(not target.is_symlink(), 'Symlinks are not allowed')
    require(target.resolve().is_relative_to(base.resolve()) and target.is_file(), 'Referenced file is missing or outside the content directory')
    return target


def load_json(path):
    require(path.stat().st_size <= 1024 * 1024, 'Content JSON exceeds 1 MiB')
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON property')
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=no_duplicates)


def normalized_image(path):
    require(0 < path.stat().st_size <= MAX_BYTES, 'Referenced image must be at most 10 MiB')
    expected = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP'}.get(path.suffix.lower())
    require(expected is not None, 'Only JPEG, PNG, and WebP images are supported')
    raw = path.read_bytes()
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw), formats=['JPEG', 'PNG', 'WEBP']) as check:
            require(check.format == expected, 'Image extension and decoded format do not match')
            require(check.width * check.height <= Image.MAX_IMAGE_PIXELS, 'Image exceeds 25 megapixels')
            require(getattr(check, 'n_frames', 1) == 1, 'Animated images are not supported')
            check.verify()
        with Image.open(io.BytesIO(raw), formats=['JPEG', 'PNG', 'WEBP']) as original:
            original.load()
            oriented = ImageOps.exif_transpose(original)
            oriented.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
            mode = 'RGBA' if 'A' in oriented.getbands() or 'transparency' in oriented.info else 'RGB'
            pixels = oriented.convert(mode)
            clean = Image.new(mode, pixels.size)
            clean.paste(pixels)
            encoded = io.BytesIO()
            clean.save(encoded, format='WEBP', quality=88, method=4)
            payload = encoded.getvalue()
    return hashlib.sha256(payload).hexdigest() + '.webp', payload


def validate_content(drafts):
    profile = load_json(safe_file(drafts, 'content/profile.json'))
    projects = load_json(safe_file(drafts, 'content/projects.json'))
    keys(profile, {'name', 'github', 'locales'}, 'profile')
    text(profile['name'], 'name')
    https_url(profile['github'])
    keys(profile['locales'], LANGUAGES, 'profile.locales')
    for lang, content in profile['locales'].items():
        keys(content, PROFILE_FIELDS, 'profile.' + lang)
        for key, value in content.items():
            text(value, key)
    require(isinstance(projects, list) and len(projects) <= 100, 'Expected at most 100 projects')
    ids, orders, images = set(), set(), {}
    featured_count = 0
    for project in projects:
        required = {'id', 'order', 'example', 'image', 'url', 'locales'}
        require(isinstance(project, dict), 'project: expected an object')
        keys(project, required | (set(project) & {'featured', 'tags'}), 'project')
        require(type(project.get('featured', False)) is bool, 'featured must be true or false')
        featured_count += project.get('featured', False)
        require(featured_count <= 1, 'Only one repository can be featured')
        tags = project.get('tags', [])
        require(isinstance(tags, list) and len(tags) <= 8, 'Expected at most eight repository tags')
        for tag in tags:
            text(tag, 'tag')
            require(len(tag) <= 40 and '\n' not in tag and '\t' not in tag, 'Tags must be short single-line text')
        require(len(tags) == len(set(tags)), 'Duplicate repository tag')
        require(isinstance(project['id'], str) and re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', project['id']), 'Invalid project ID')
        require(project['id'] not in ids, 'Duplicate project ID')
        ids.add(project['id'])
        require(type(project['order']) is int and 0 <= project['order'] <= 10000 and project['order'] not in orders, 'Project order must be a unique nonnegative integer')
        orders.add(project['order'])
        require(type(project['example']) is bool, 'example must be true or false')
        if project['url'] is not None:
            https_url(project['url'])
            parsed = urlsplit(project['url'])
            require(parsed.netloc == 'github.com' and re.fullmatch(r'/[A-Za-z0-9-]+/[A-Za-z0-9_.-]+/?', parsed.path)
                    and not parsed.query and not parsed.fragment, 'Repository URL must point to a GitHub repository')
        require(project['example'] or project['url'] is not None, 'A repository needs a GitHub URL')
        require(not project.get('featured', False) or not project['example'], 'An example cannot be featured')
        keys(project['locales'], LANGUAGES, 'project.locales')
        for lang, content in project['locales'].items():
            keys(content, {'title', 'description', 'alt'}, 'project.' + lang)
            for key, value in content.items():
                text(value, key, allow_empty=(key == 'alt' and project['image'] is None))
        if project['image'] is not None:
            filename = project['image']
            require(isinstance(filename, str) and filename.startswith('media/'), 'Image path must start with media/')
            if filename not in images:
                images[filename] = normalized_image(safe_file(drafts, filename))
    return profile, sorted(projects, key=lambda p: p['order']), images


def load_ui():
    """Interface copy lives beside the template; both languages must define the same keys."""
    ui = load_json(ROOT / 'templates' / 'ui.json')
    keys(ui, LANGUAGES, 'ui')
    expected = set(ui[LANGUAGES[0]])
    require(not expected & (PROFILE_FIELDS | COMPUTED_FIELDS), 'ui: keys collide with content fields')
    for lang in LANGUAGES:
        keys(ui[lang], expected, 'ui.' + lang)
        for key, value in ui[lang].items():
            text(value, 'ui.' + key)
    return ui


def escaped(value, multiline=True):
    result = html.escape(value, quote=True)
    return result.replace('\n', '<br>') if multiline else result.replace('\n', ' ')


def github_handle(url):
    parsed = urlsplit(url)
    return parsed.path.strip('/').split('/')[0] or parsed.hostname


def language_nav(current):
    links = []
    for lang in LANGUAGES:
        state = ' aria-current="page"' if lang == current else f' hreflang="{lang}"'
        links.append(f'<a href="../{lang}/" lang="{lang}"{state}>{lang.upper()}</a>')
    return '<span aria-hidden="true">/</span>'.join(links)


REPOSITORY_ICON = '<svg class="repository-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5c-2.5-2-6-2-9-1v15c3-1 6.5-1 9 1 2.5-2 6-2 9-1V4c-3-1-6.5-1-9 1Z"/><path d="M12 5v15"/></svg>'
EXTERNAL_ICON = '<svg class="external-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12 12 4M4 4h8v8"/></svg>'


def repository_tags(project, ui):
    tags = project.get('tags', [])
    if not tags:
        return ''
    items = ''.join(f'<li>{escaped(tag, False)}</li>' for tag in tags)
    return f'<ul class="tags" aria-label="{escaped(ui["tagsLabel"], False)}">{items}</ul>'


def repository_link(project, content, ui):
    if project['url']:
        label = escaped(ui['viewRepository'])
        return f'<a class="repository-link" href="{escaped(project["url"], False)}">{label}<span class="sr-only">: {escaped(content["title"])}</span>{EXTERNAL_ICON}</a>'
    return f'<p class="muted">{escaped(ui["pendingLabel"])}</p>'


def featured_repository(projects, ui):
    project = next((p for p in projects if p.get('featured', False)), None)
    if project is None:
        return ''
    content = project['locales'][ui['lang']]
    return (f'<aside class="featured-repository" aria-labelledby="featured-title">'
            f'<p class="featured-label">{REPOSITORY_ICON}{escaped(ui["featuredLabel"])}</p>'
            f'<h2 id="featured-title">{escaped(content["title"])}</h2>'
            f'<p class="featured-description">{escaped(content["description"])}</p>'
            f'{repository_tags(project, ui)}{repository_link(project, content, ui)}</aside>')


def cards(projects, images, ui):
    if not projects:
        return f'<li class="empty-repositories"><p>{escaped(ui["emptyRepositories"])}</p></li>'
    rendered = []
    for project in projects:
        content = project['locales'][ui['lang']]
        if project['image']:
            name = images[project['image']][0]
            cover = f'<img class="repository-image" src="../assets/media/{name}" alt="{escaped(content["alt"], False)}" loading="lazy" decoding="async">'
        else:
            cover = REPOSITORY_ICON
        label = f'<p class="example-label">{escaped(ui["exampleLabel"])}</p>' if project['example'] else ''
        rendered.append(
            f'        <li class="repository-row" id="repository-{project["id"]}">{cover}'
            f'<div class="repository-copy">{label}<h3>{escaped(content["title"])}</h3>'
            f'<p class="repository-description">{escaped(content["description"], False)}</p>{repository_tags(project, ui)}</div>'
            f'{repository_link(project, content, ui)}</li>')
    return '\n'.join(rendered)


def render_page(template, profile, projects, images, ui, lang):
    strings = dict(ui[lang], lang=lang)
    caption = ''
    if any(p['example'] for p in projects):
        caption = f'<p class="section-caption">{escaped(strings["exampleCaption"])}</p>'
    values = {key: escaped(value, key not in SINGLE_LINE_FIELDS) for key, value in strings.items()}
    values.update({key: escaped(value, key not in SINGLE_LINE_FIELDS) for key, value in profile['locales'][lang].items()})
    values.update(
        lang=lang,
        siteUrl=escaped(SITE_URL, False),
        name=escaped(profile['name']),
        github=escaped(profile['github'], False),
        githubHandle=escaped(github_handle(profile['github']), False),
        languageNav=language_nav(lang),
        projectCaption=caption,
        projects=cards(projects, images, strings),
        featuredRepository=featured_repository(projects, strings),
    )
    placeholders = set(PLACEHOLDER.findall(template))
    require(placeholders <= set(values), 'Template uses an undefined field')
    require(PROFILE_FIELDS | COMPUTED_FIELDS <= placeholders, 'Template omits part of the content contract')
    return PLACEHOLDER.sub(lambda m: values[m[1]], template)


def build(drafts, output):
    drafts, output = Path(drafts).resolve(), Path(output).resolve()
    require(not output.exists(), 'Output must be a new directory; existing output is never overwritten')
    require(not drafts.is_relative_to(output), 'Output cannot contain the draft source')
    profile, projects, images = validate_content(drafts)
    ui = load_ui()
    template = (ROOT / 'templates' / 'page.html').read_text(encoding='utf-8')
    pages = {lang: render_page(template, profile, projects, images, ui, lang) for lang in LANGUAGES}
    # All input validation and rendering finished before producing any output.
    output.mkdir(parents=True)
    for rel in STATIC_FILES:
        destination = output / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / 'docs' / rel, destination)
    for lang, page in pages.items():
        (output / lang).mkdir()
        (output / lang / 'index.html').write_text(page, encoding='utf-8', newline='\n')
    if images:
        media = output / 'assets' / 'media'
        media.mkdir(parents=True)
        for name, payload in images.values():
            (media / name).write_bytes(payload)
    require(sum(p.stat().st_size for p in output.rglob('*') if p.is_file()) < MAX_SITE_BYTES, 'Published site exceeds the 900 MiB project budget')
    return len(projects), len(images)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--content', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        count, media = build(args.content, args.out)
        print(f'Validated and built {count} projects and {media} referenced images.')
    except Exception as error:
        # Do not echo draft text, paths, secrets, or decoder traces into logs.
        print(f'Build rejected ({type(error).__name__}). Check schema, HTTPS links, image format/size, and local paths.')
        raise SystemExit(1)
