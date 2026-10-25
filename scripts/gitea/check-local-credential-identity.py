#!/usr/bin/env python3
"""TD-440: inspect credential account metadata, never retrieve passwords.

Owner supplies the current admin login inventory. Unknown credential helpers
are inconclusive (exit 2), not a clean bill of health. osxkeychain queries omit
-g/-w; no git credential fill or Keychain dump is ever used.
"""
import argparse
import re
import subprocess
import sys


def check(host, admins, run=subprocess.run):
    failures, unknown = [], []
    config = run(['git', 'config', '--get-urlmatch', 'credential', f'http://{host}'],
                 capture_output=True, text=True)
    if config.returncode not in (0, 1):
        return [], ['cannot inspect credential configuration']
    for line in config.stdout.splitlines():
        key, _, value = line.partition(' ')
        if key.endswith('.username') and value in admins:
            failures.append('git configured username is an admin')
        if key.endswith('.helper') and value and value != 'osxkeychain':
            # A shell helper, store or cache can supply a different identity.
            unknown.append('a credential helper needs an account-metadata audit')
    server = host.split(':')[0]
    for account in admins:
        result = run(['security', 'find-internet-password', '-s', server, '-a', account],
                     capture_output=True, text=True)
        if result.returncode == 0:
            failures.append(f'admin account {account} has a Keychain entry for {server}')
        elif result.returncode != 44:  # errSecItemNotFound
            unknown.append('Keychain metadata lookup failed')
    return failures, unknown


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', default='192.168.10.73:30300')
    p.add_argument('--admin', action='append', required=True)
    args = p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9._-]+(?::[0-9]+)?', args.host):
        p.error('invalid host')
    failures, unknown = check(args.host, args.admin)
    for item in failures:
        print('FAIL: ' + item)
    for item in unknown:
        print('INCONCLUSIVE: ' + item)
    if failures:
        return 1
    if unknown:
        return 2
    print('PASS: no listed admin credential metadata; admin inventory completeness is Owner-verified')
    return 0


if __name__ == '__main__':
    sys.exit(main())
