"""Refresh and publish through the owner's existing Git setup."""

import subprocess
import sys
from pathlib import Path

from knot.shared.storage import validate_dataset_paths
from knot.writing.datasets import TRANSIENTS, is_dataset


def _repository(data_root):
    data_root = validate_dataset_paths(data_root)

    def git(*args, input=None):
        result = subprocess.run(
            ['git', '-C', str(data_root), '-c', 'status.relativePaths=false', *args],
            capture_output=True,
            text=True,
            input=input,
        )
        if result.returncode:
            raise ValueError(result.stderr.strip() or result.stdout.strip() or 'Git failed')
        return result.stdout if '-z' in args else result.stdout.strip()

    root = Path(git('rev-parse', '--show-toplevel')).resolve()
    standalone = data_root == root and is_dataset(root)
    if not standalone and data_root != root / 'data':
        raise ValueError(
            'Git synchronisation requires a dataset repository root or its data/ directory'
        )
    prefix = '' if standalone else 'data/'
    branch = git('symbolic-ref', '--quiet', '--short', 'HEAD')
    try:
        git('rev-parse', '--verify', '@{upstream}')
        tracking = True
    except ValueError:
        tracking = False
    try:
        remote = git('config', '--get', f'branch.{branch}.remote')
        destination = git('config', '--get', f'branch.{branch}.merge')
    except ValueError as exc:
        if standalone and git('remote').splitlines() == ['origin'] and not tracking:
            remote, destination = 'origin', f'refs/heads/{branch}'
        else:
            raise ValueError(
                'Configure a Git upstream for this branch before synchronising'
            ) from exc
    if remote == '.' or not destination.startswith('refs/heads/'):
        raise ValueError('Git synchronisation requires an upstream branch on a remote')
    return git, remote, destination, prefix, tracking


def refresh(data_root):
    git, remote, destination, prefix, tracking = _repository(data_root)
    if not tracking:
        raise ValueError(
            'No upstream commits available; use knot push for the initial dataset commit'
        )
    changes = git('status', '--porcelain', '--untracked-files=all')
    if changes:
        raise ValueError(
            'Refresh stopped: uncommitted changes exist. Commit your work first '
            '(knot push handles knowledge data; application edits need a separate commit).'
            f'\n{changes}'
        )
    print(f'Refreshing from: {remote} {destination}', file=sys.stderr)
    try:
        result = git(
            'pull', '--ff-only', '--no-rebase', '--no-autostash', '--', remote, destination
        )
        validate_dataset_paths(data_root)
    except ValueError as exc:
        raise ValueError(
            f'Refresh failed. Resolve the Git issue before retrying knot refresh.\n{exc}'
        ) from exc
    print(result or 'Refresh complete.')


def push(data_root):
    from knot.interfaces.note_cli import _ask

    git, remote, destination, prefix, tracking = _repository(data_root)
    excluded = tuple(prefix + name for name in TRANSIENTS)
    staged = git('diff', '--cached', '--no-relative', '--name-only', '-z').split('\0')
    if any(
        name
        and (
            not name.startswith(prefix)
            or any(name.startswith(p) if p.endswith('/') else name == p for p in excluded)
        )
        for name in staged
    ):
        raise ValueError('Files outside knowledge data are staged; commit or unstage them first')
    paths = [
        ':(top)' + (prefix.rstrip('/') or '*'),
        *[f':(top,exclude){p.rstrip("/")}' for p in excluded],
    ]
    changes = git('status', '--short', '--untracked-files=all', '--', *paths)
    if tracking:
        pending = git('log', '--oneline', '@{upstream}..HEAD')
    else:
        try:
            pending = git('log', '--oneline', 'HEAD')
        except ValueError:
            pending = ''
    print(f'Push destination: {remote} {destination}', file=sys.stderr)
    if pending:
        print(f'Pending commits (all will be pushed):\n{pending}', file=sys.stderr)
    if changes:
        print(f'Knowledge changes to commit:\n{changes}', file=sys.stderr)
        message = _ask('Commit message (Enter to cancel):').strip()
        if not message:
            print('Cancelled; nothing staged or committed.', file=sys.stderr)
            return
        # Enumerate actual changes: Git can reject ignored paths even when they
        # appear as exclusions in an add pathspec. NULs preserve unusual names.
        changed_files = git(
            'ls-files',
            '--full-name',
            '-z',
            '--modified',
            '--deleted',
            '--others',
            '--exclude-standard',
            '--',
            *paths,
        )
        if changed_files:
            git(
                'add',
                '-A',
                '--pathspec-from-file=-',
                '--pathspec-file-nul',
                input=''.join(
                    f':(top,literal){name}\0' for name in changed_files.split('\0') if name
                ),
            )
        print(git('commit', '-m', message), file=sys.stderr)
    elif not pending:
        print('No knowledge changes or pending commits to push.', file=sys.stderr)
        return
    try:
        git('push', '--set-upstream', '--', remote, f'HEAD:{destination}')
    except ValueError as exc:
        raise ValueError(
            f'Push failed; local commits are retained. Resolve the Git error and retry '
            f'knot push.\n{exc}'
        ) from exc
    print('Knowledge committed and pushed.' if changes else 'Pending commits pushed.')
