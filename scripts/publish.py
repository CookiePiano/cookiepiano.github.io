"""Publish a validated output tree using an ephemeral, repository-scoped App token."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from site_config import CONTENT_REPOSITORY_NAME, OWNER_ID, PUBLIC_FILES, PUBLIC_REPOSITORY_ID, SITE_URL

# Addressed by ID so a repository rename cannot redirect writes elsewhere.
API_ROOT = 'https://api.github.com/repositories/' + PUBLIC_REPOSITORY_ID
MEDIA_FILE = re.compile(r'assets/media/[a-f0-9]{64}\.webp')


def authorized(env):
    owner = env.get('GITHUB_REPOSITORY_OWNER', '')
    return (env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and env.get('GITHUB_REPOSITORY_OWNER_ID') == OWNER_ID
            and bool(owner)
            and env.get('GITHUB_REPOSITORY') == owner + '/' + CONTENT_REPOSITORY_NAME
            and env.get('GITHUB_REF') == 'refs/heads/main'
            and env.get('GITHUB_ACTOR_ID') == OWNER_ID
            and env.get('GITHUB_TRIGGERING_ACTOR') == owner
            and env.get('CONFIRM_PUBLICATION') == 'true')


def collect_output(folder):
    files = {}
    for path in folder.rglob('*'):
        if path.is_symlink():
            raise ValueError('Symlink in output')
        if path.is_file():
            rel = path.relative_to(folder).as_posix()
            if rel not in PUBLIC_FILES and not MEDIA_FILE.fullmatch(rel):
                raise ValueError('Unexpected output file')
            files[rel] = path.read_bytes()
    if not PUBLIC_FILES <= set(files):
        raise ValueError('Missing output file')
    return files


def git_sha(payload):
    return hashlib.sha1(b'blob ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()


def tree_changes(existing, files):
    desired = {'docs/' + name: data for name, data in files.items()}
    changes = [(path, payload) for path, payload in desired.items() if existing.get(path) != git_sha(payload)]
    changes += [(path, None) for path in existing if path.startswith('docs/') and path not in desired]
    return changes


def published_matches(files, marker):
    for name, body in files.items():
        if name == '.nojekyll':
            continue
        try:
            with urlopen(SITE_URL + name + '?publication=' + marker, timeout=20) as response:
                if response.read() != body:
                    return False
        except (HTTPError, OSError):
            return False
    return True


def main(folder):
    if not authorized(os.environ):
        raise PermissionError('Only the owner may publish a manually confirmed main-branch draft')
    token = os.environ.get('PUBLISH_TOKEN')
    if not token:
        raise PermissionError('Publishing App is not configured')
    files = collect_output(Path(folder))

    def api(method, route, body=None):
        req = Request(API_ROOT + route,
                      data=None if body is None else json.dumps(body).encode(), method=method,
                      headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'pistco-site-publisher', 'Content-Type': 'application/json'})
        with urlopen(req, timeout=30) as response:
            return json.load(response)

    head = api('GET', '/git/ref/heads/main')['object']['sha']
    tree_sha = api('GET', '/git/commits/' + head)['tree']['sha']
    tree = api('GET', '/git/trees/' + tree_sha + '?recursive=1')
    if tree.get('truncated'):
        raise ValueError('Repository tree is truncated; refusing partial publication')
    existing = {f['path']: f['sha'] for f in tree['tree'] if f['type'] == 'blob'}
    entries = []
    for path, payload in tree_changes(existing, files):
        sha = None
        if payload is not None:
            sha = api('POST', '/git/blobs', {'encoding': 'base64', 'content': base64.b64encode(payload).decode()})['sha']
        entries.append({'path': path, 'mode': '100644', 'type': 'blob', 'sha': sha})
    published = head
    if entries:
        new_tree = api('POST', '/git/trees', {'base_tree': tree_sha, 'tree': entries})['sha']
        published = api('POST', '/git/commits', {'message': 'Publish approved bilingual portfolio', 'tree': new_tree, 'parents': [head]})['sha']
        # A concurrent update rejects this non-fast-forward change. Never force or retry over it.
        api('PATCH', '/git/refs/heads/main', {'sha': published, 'force': False})
    summary = Path(os.environ['GITHUB_STEP_SUMMARY'])
    with summary.open('a', encoding='utf-8') as stream:
        stream.write(f'## Publication\n- Private draft: `{os.environ["GITHUB_SHA"]}`\n- Engine: `{os.environ.get("ENGINE_SHA", "unknown")}`\n- Public commit: `{published}`\n- Site: {SITE_URL}\n')
    attempts = 36
    for attempt in range(attempts):
        if published_matches(files, published):
            with summary.open('a', encoding='utf-8') as stream:
                stream.write('- Verification: all public files match this publication.\n')
            print('Public site verified. Publication complete.')
            return
        if attempt < attempts - 1:
            time.sleep(10)
    raise RuntimeError('Public commit saved, but Pages verification timed out; inspect the public Pages deployment before retrying')


if __name__ == '__main__':
    import sys
    try:
        main(sys.argv[1])
    except Exception as error:
        # The exception type is sufficient; HTTP bodies and credentials never enter logs.
        print(f'Publication stopped ({type(error).__name__}). Check permissions, concurrent updates, and Pages status.')
        raise SystemExit(1)
