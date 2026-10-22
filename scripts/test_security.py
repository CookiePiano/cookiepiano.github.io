"""Regression checks for the private/public boundary, rendering, and publishing gate."""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from PIL import Image

import build
import publish
import site_config


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.draft = self.root / 'draft'
        (self.draft / 'content').mkdir(parents=True)
        (self.draft / 'media').mkdir()
        local = {k: 'Test ' + k for k in build.PROFILE_FIELDS}
        self.profile = {'name': 'CookiePiano', 'github': 'https://github.com/CookiePiano', 'locales': {'ko': local.copy(), 'en': local.copy()}}
        self.project = {'id': 'test-project', 'order': 1, 'example': True, 'image': None, 'url': None, 'locales': {lang: {'title': 'Example', 'description': 'Test description', 'alt': ''} for lang in ('ko', 'en')}}
        self.projects = [self.project]

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        for name, value in [('profile', self.profile), ('projects', self.projects)]:
            (self.draft / 'content' / (name + '.json')).write_text(json.dumps(value), encoding='utf-8')

    def render(self):
        self.save()
        out = self.root / 'output'
        build.build(self.draft, out)
        return out

    def image(self, filename='test.png', fmt='PNG'):
        path = self.draft / 'media' / filename
        Image.new('RGB', (12, 10), 'blue').save(path, format=fmt)
        self.project['image'] = 'media/' + filename
        for content in self.project['locales'].values():
            content['alt'] = 'Example image'
        return path

    def test_private_files_and_unused_images_never_export(self):
        (self.draft / 'PRIVATE_CHECK.txt').write_text('NEVER-PUBLIC')
        (self.draft / 'media/unused.svg').write_text('<script>NEVER-PUBLIC</script>')
        out = self.render()
        files = publish.collect_output(out)
        self.assertEqual(set(files), site_config.PUBLIC_FILES)
        self.assertNotIn(b'NEVER-PUBLIC', b''.join(files.values()))

    def test_html_is_text_not_executable(self):
        self.project['locales']['ko']['title'] = '<script>alert(1)</script>'
        self.profile['locales']['ko']['headline'] = '{{github}}<img src=x onerror=alert(1)>'
        result = (self.render() / 'ko/index.html').read_text(encoding='utf-8')
        self.assertIn('&lt;script&gt;', result)
        self.assertNotIn('<script>', result)
        self.assertNotIn('<img src=x', result)
        # Content is inserted once; placeholder syntax inside content is never expanded.
        self.assertIn('{{github}}', result)

    def test_languages_render_equivalent_structure(self):
        out = self.render()
        pages = {lang: (out / lang / 'index.html').read_text(encoding='utf-8') for lang in site_config.LANGUAGES}
        tags = {lang: re.findall(r'<(\w+)[\s>]', page) for lang, page in pages.items()}
        self.assertEqual(tags['ko'], tags['en'])
        for lang, page in pages.items():
            self.assertIn(f'<html lang="{lang}">', page)
            self.assertIn(f'<link rel="canonical" href="{site_config.SITE_URL}{lang}/">', page)
            self.assertIn(f'<a href="../{lang}/" lang="{lang}" aria-current="page">', page)
            self.assertEqual(page.count('aria-current="page"'), 1)
            self.assertNotIn('{{', page)
            self.assertIn('@CookiePiano', page)

    def test_ui_strings_must_match_between_languages(self):
        ui = build.load_ui()
        self.assertEqual(set(ui['ko']), set(ui['en']))
        broken = copy.deepcopy(ui)
        del broken['en']['skipLink']
        original = build.load_json
        build.load_json = lambda path: broken
        try:
            with self.assertRaises(ValueError):
                build.load_ui()
        finally:
            build.load_json = original

    def test_featured_repository_is_independent_of_list_order(self):
        self.project.update(example=False, url='https://github.com/CookiePiano/example', featured=True, tags=['Python'])
        second = copy.deepcopy(self.project)
        second.update(id='second', order=0, featured=False, url='https://github.com/CookiePiano/second')
        for locale in second['locales'].values():
            locale['title'] = 'Second repository'
        self.projects.append(second)
        page = (self.render() / 'ko/index.html').read_text(encoding='utf-8')
        self.assertEqual(page.count('id="featured-title"'), 1)
        self.assertIn('id="featured-title">Example</h2>', page)
        self.assertLess(page.index('id="repository-second"'), page.index('id="repository-test-project"'))
        self.assertIn('<li>Python</li>', page)

    def test_multiple_featured_repositories_and_featured_examples_rejected(self):
        self.project['featured'] = True
        self.save()
        with self.assertRaises(ValueError):
            build.validate_content(self.draft)
        self.project.update(example=False, url='https://github.com/CookiePiano/example')
        second = copy.deepcopy(self.project)
        second.update(id='second', order=2)
        self.projects.append(second)
        self.save()
        with self.assertRaises(ValueError):
            build.validate_content(self.draft)

    def test_repository_urls_must_be_actual_github_path_shapes(self):
        self.project['example'] = False
        for url in (None, 'https://example.com/repository', 'https://github.com/CookiePiano',
                    'https://github.com/CookiePiano/example/tree/main', 'https://github.com:444/CookiePiano/example',
                    'https://github.com/CookiePiano/example?tab=readme', 'https://github.com.evil.test/a/b'):
            self.project['url'] = url
            self.save()
            with self.subTest(url=url), self.assertRaises(ValueError):
                build.validate_content(self.draft)

    def test_tags_are_validated_and_escaped(self):
        for tags in ('Python', ['same', 'same'], ['x' * 41], ['line\nbreak'], [1], ['']):
            self.project['tags'] = tags
            self.save()
            with self.subTest(tags=tags), self.assertRaises(ValueError):
                build.validate_content(self.draft)
        self.project['tags'] = ['<img src=x onerror=alert(1)>']
        page = (self.render() / 'ko/index.html').read_text(encoding='utf-8')
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', page)
        self.assertNotIn('<img src=x', page)

    def test_empty_repository_list_renders_in_both_languages(self):
        self.projects = []
        out = self.render()
        for lang in site_config.LANGUAGES:
            page = (out / lang / 'index.html').read_text(encoding='utf-8')
            self.assertIn('class="empty-repositories"', page)
            self.assertNotIn('id="featured-title"', page)
            self.assertIn('https://github.com/CookiePiano', page)

    def test_single_repository_without_optional_fields_and_theme_asset(self):
        self.project.update(example=False, url='https://github.com/CookiePiano/example')
        out = self.render()
        page = (out / 'en/index.html').read_text(encoding='utf-8')
        self.assertEqual(page.count('class="repository-row"'), 1)
        self.assertNotIn('id="featured-title"', page)
        self.assertTrue((out / 'assets/theme.js').is_file())
        self.assertLess(page.index('src="../assets/theme.js"'), page.index('href="../assets/styles.css"'))

    def test_dangerous_and_credential_urls_rejected(self):
        for url in ('javascript:alert(1)', 'data:text/html,test', 'http://example.com', 'https://a:b@example.com', 'https://example.com\\evil', 'https://example.com\n'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                build.https_url(url)

    def test_missing_translation_rejected(self):
        del self.project['locales']['en']
        with self.assertRaises(ValueError):
            self.render()
        self.assertFalse((self.root / 'output').exists())

    def test_path_escape_rejected(self):
        for name in ('../secret.png', '/secret.png', 'media/../secret.png', 'media\\test.png', 'C:/secret.png'):
            with self.subTest(path=name), self.assertRaises(ValueError):
                build.safe_file(self.draft, name)

    def test_symlink_rejected(self):
        target = self.root / 'secret.png'
        Image.new('RGB', (1, 1)).save(target)
        link = self.draft / 'media/link.png'
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest('OS does not permit this process to create a symlink')
        with self.assertRaises(ValueError):
            build.safe_file(self.draft, 'media/link.png')

    def test_fake_image_rejected(self):
        path = self.image()
        path.write_text('<html><script>alert(1)</script></html>')
        with self.assertRaises(Exception):
            self.render()
        self.assertFalse((self.root / 'output').exists())

    def test_format_mismatch_and_oversize_rejected(self):
        path = self.image('wrong.png', 'JPEG')
        with self.assertRaises(ValueError):
            build.normalized_image(path)
        path.write_bytes(b'x' * (build.MAX_BYTES + 1))
        with self.assertRaises(ValueError):
            build.normalized_image(path)

    def test_images_reencoded_without_metadata(self):
        path = self.image('photo.jpg', 'JPEG')
        exif = Image.Exif()
        exif[270] = 'PRIVATE-EXIF-MARKER'
        Image.new('RGB', (12, 10), 'blue').save(path, exif=exif)
        out = self.render()
        images = list((out / 'assets/media').glob('*.webp'))
        self.assertEqual(len(images), 1)
        with Image.open(images[0]) as result:
            self.assertFalse(result.getexif())
        self.assertNotIn(b'PRIVATE-EXIF-MARKER', images[0].read_bytes())
        self.assertIn('assets/media/' + images[0].name, (out / 'en/index.html').read_text(encoding='utf-8'))

    def test_duplicate_ids_orders_missing_image_rejected(self):
        self.projects.append(copy.deepcopy(self.project))
        with self.assertRaises(ValueError):
            self.render()
        self.projects.pop()
        self.project['image'] = 'media/missing.png'
        for locale in self.project['locales'].values():
            locale['alt'] = 'Missing'
        with self.assertRaises(ValueError):
            self.render()

    def test_existing_output_never_overwritten(self):
        self.save()
        out = self.root / 'output'
        out.mkdir()
        (out / 'keep.txt').write_text('keep')
        with self.assertRaises(ValueError):
            build.build(self.draft, out)
        self.assertEqual((out / 'keep.txt').read_text(), 'keep')

    def test_publication_output_allowlist(self):
        out = self.render()
        (out / 'private.json').write_text('SECRET')
        with self.assertRaises(ValueError):
            publish.collect_output(out)

    def test_owner_manual_main_and_confirmation_all_required(self):
        env = {'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REPOSITORY': 'CookiePiano/pistco-site-content', 'GITHUB_REPOSITORY_OWNER': 'CookiePiano', 'GITHUB_REPOSITORY_OWNER_ID': '220297881', 'GITHUB_REF': 'refs/heads/main', 'GITHUB_ACTOR_ID': '220297881', 'GITHUB_TRIGGERING_ACTOR': 'CookiePiano', 'CONFIRM_PUBLICATION': 'true'}
        self.assertTrue(publish.authorized(env))
        for field in env:
            denied = dict(env, **{field: 'not-authorized'})
            self.assertFalse(publish.authorized(denied), field)
            missing = {k: v for k, v in env.items() if k != field}
            self.assertFalse(publish.authorized(missing), field)
        # A future rename keeps working because identity is the immutable owner ID.
        renamed = dict(env, GITHUB_REPOSITORY='NewName/pistco-site-content', GITHUB_REPOSITORY_OWNER='NewName', GITHUB_TRIGGERING_ACTOR='NewName')
        self.assertTrue(publish.authorized(renamed))
        impostor = dict(renamed, GITHUB_REPOSITORY_OWNER_ID='1')
        self.assertFalse(publish.authorized(impostor))

    def test_publication_preserves_non_site_files_and_removes_old_media(self):
        changes = publish.tree_changes({'README.md': 'a', '.github/workflows/test.yml': 'b', 'docs/old.png': 'c', 'docs/index.html': publish.git_sha(b'old')}, {'index.html': b'new'})
        self.assertEqual(changes, [('docs/index.html', b'new'), ('docs/old.png', None)])

    def test_static_pages_use_current_identity(self):
        for rel in site_config.STATIC_FILES:
            if rel.endswith('.html'):
                page = (build.ROOT / 'docs' / rel).read_text(encoding='utf-8')
                with self.subTest(page=rel):
                    # The retired account name could be claimed by someone else.
                    self.assertNotIn('github.com/PISTCO', page)
                    self.assertNotIn('pistco.github.io', page)
                    for url in re.findall(r'https://[a-z.]+\.github\.io/', page):
                        self.assertEqual(url, site_config.SITE_URL)

    def test_publisher_targets_site_and_repository_by_identity(self):
        self.assertTrue(site_config.SITE_URL.startswith('https://') and site_config.SITE_URL.endswith('/'))
        self.assertTrue(publish.API_ROOT.endswith('/repositories/' + site_config.PUBLIC_REPOSITORY_ID))


if __name__ == '__main__':
    unittest.main()
