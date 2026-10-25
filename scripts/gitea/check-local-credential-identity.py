#!/usr/bin/env python3
"""TD-440: inspect credential account metadata, never retrieve passwords.

Run in each real checkout, or repeat --checkout. Owner supplies the current
admin/host inventory. Unknown helpers or origins are inconclusive (exit 2).
osxkeychain queries omit -g/-w; no credential lookup or Keychain dump is used.
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit


def credential_entries(checkout, run):
    # --get-urlmatch collapses repeated helpers; it cannot be combined with
    # --get-all/--show-origin. Preserve order, resets and included-file origins.
    result = run(['git', '-C', str(checkout), 'config', '--includes', '--null',
                  '--show-origin', '--get-regexp', r'^credential\.(.*\.)?(helper|username)$'],
                 capture_output=True, text=True)
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise ValueError('cannot inspect credential configuration')
    fields = result.stdout.split('\0')
    if fields.pop() != '' or len(fields) % 2:
        raise ValueError('cannot parse credential configuration origins')
    entries = []
    for origin, record in zip(fields[::2], fields[1::2]):
        key, separator, value = record.partition('\n')
        if not separator:
            raise ValueError('credential configuration has no value')
        entries.append((origin, key, value))
    return entries


def matches(key, url, run):
    scope, _, _ = key[len('credential.'):].rpartition('.')
    if not scope:
        return True
    # Ask Git to match each context independently: credential.c selects ALL
    # matching entries, not just the most-specific one chosen by get-urlmatch.
    # Partial/malformed contexts cannot be proven by this matcher: fail closed.
    if '://' not in scope:
        raise ValueError('partial credential URL context needs a metadata audit')
    escaped = scope.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    config = f'[credential "{escaped}"]\n helper = metadata-probe\n'
    result = run(['git', 'config', '--file', '-', '--get-urlmatch', 'credential.helper', url],
                 input=config, capture_output=True, text=True)
    if result.returncode not in (0, 1) or (result.returncode == 0 and result.stdout.strip() != 'metadata-probe'):
        raise ValueError('cannot match credential URL context')
    return result.returncode == 0


def checkout_urls(checkout, run):
    result = run(['git', '-C', str(checkout), 'remote'], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('cannot enumerate checkout remotes')
    urls = set()
    for remote in result.stdout.splitlines():
        for mode in ([], ['--push']):
            # get-url expands insteadOf/pushInsteadOf and includes every URL.
            result = run(['git', '-C', str(checkout), 'remote', 'get-url', '--all', *mode, remote],
                         capture_output=True, text=True)
            if result.returncode:
                raise ValueError('cannot enumerate fetch/push URLs')
            urls.update(result.stdout.splitlines())
    return urls


def check(host, admins, run=subprocess.run, checkout='.'):
    failures, unknown = [], []
    try:
        entries = credential_entries(checkout, run)
        urls = [url for url in checkout_urls(checkout, run)
                if urlsplit(url).netloc.rsplit('@', 1)[-1].lower() == host.lower()]
        if not urls:
            unknown.append('no real fetch/push URL found for the requested host')
        for url in sorted(urls):
            parsed = urlsplit(url)
            if parsed.scheme not in ('http', 'https') or parsed.password is not None:
                unknown.append('remote URL needs a separate credential metadata audit')
                continue
            helpers, username = [], unquote(parsed.username) if parsed.username else None
            for origin, key, value in entries:
                try:
                    if not matches(key, url, run):
                        continue
                except ValueError as error:
                    unknown.append(str(error))
                    continue
                if not origin.startswith('file:') or not (Path(checkout) / origin[5:]).is_file():
                    unknown.append('credential configuration has an unknown origin')
                if key.endswith('.helper'):
                    if value:
                        helpers.append((origin, value))
                    else:
                        helpers.clear()
                elif key.endswith('.username') and parsed.username is None:
                    username = value
            if username in admins:
                failures.append('git configured URL/username is an admin')
            for origin, helper in helpers:
                if helper != 'osxkeychain':
                    # Never execute helpers or echo their bodies (may contain keys).
                    unknown.append(f'a credential helper needs an account-metadata audit (origin: {origin})')
    except (OSError, ValueError) as error:
        unknown.append(str(error))
    server = host.split(':')[0]
    for account in admins:
        try:
            result = run(['security', 'find-internet-password', '-s', server, '-a', account],
                         capture_output=True, text=True)
        except OSError:
            unknown.append('Keychain metadata lookup unavailable')
            continue
        if result.returncode == 0:
            failures.append(f'admin account {account} has a Keychain entry for {server}')
        elif result.returncode != 44:  # errSecItemNotFound
            unknown.append('Keychain metadata lookup failed')
    return list(dict.fromkeys(failures)), list(dict.fromkeys(unknown))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', default='192.168.10.73:30300')
    p.add_argument('--admin', action='append', required=True)
    p.add_argument('--checkout', action='append', help='real checkout path; repeat for each checkout (default: cwd)')
    args = p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9._-]+(?::[0-9]+)?', args.host):
        p.error('invalid host')
    failures, unknown = [], []
    for checkout in args.checkout or ['.']:
        bad, uncertain = check(args.host, args.admin, checkout=checkout)
        failures.extend(f'{checkout}: {item}' for item in bad)
        unknown.extend(f'{checkout}: {item}' for item in uncertain)
    for item in failures:
        print('FAIL: ' + item)
    for item in unknown:
        print('INCONCLUSIVE: ' + item)
    if failures:
        return 1
    if unknown:
        return 2
    print('PASS: no listed admin credential metadata; admin/host/checkout inventory completeness is Owner-verified')
    return 0


if __name__ == '__main__':
    sys.exit(main())
