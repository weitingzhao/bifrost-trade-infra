#!/usr/bin/env python3
"""What do I need to bring to do X? (Station, 2026-11-22; format station.requires/v1, see README.md)

Usage: howto.py            lists what can be looked up, by task
       howto.py <tool>     prints what that tool needs, where to get it, and how to check before going
"""
import pathlib
import sys

import yaml

HERE = pathlib.Path(__file__).resolve().parent / 'requires'


def load():
    return {p.stem: yaml.safe_load(p.read_text()) for p in sorted(HERE.glob('*.yaml'))}


def show(d):
    lines = [f"# {d['task']}（{d['tool']}，归 {d['owner']}）", d['how']]
    if d.get('precheck'):
        lines.append(f"办之前自查：{d['precheck']}")
    lines.append('要带：')
    for b in d['bring']:
        lines.append(f"- {b['id']}：{b['what']}")
        if b.get('command'):
            lines.append(f"  命令：{b['command']}")
        if b.get('get_from'):
            lines.append(f"  缺了去哪拿：{b['get_from']}")
    if d.get('ci_red'):
        lines.append('检查红了：')
        lines += [f"- {c['task']}：{c['means']}。{c['do']}" for c in d['ci_red']]
    if d.get('must_answer'):
        lines.append('找这条线它必须答：')
        lines += [f'- {m}' for m in d['must_answer']]
    lines.append(f"被拒的每一句话和该做什么：{HERE.name}/{d['tool']}.yaml 的 refusals")
    return '\n'.join(lines)


def main(argv):
    docs = load()
    if not argv:
        for name, d in docs.items():
            print(f"{name}\t{d['task']}（归 {d['owner']}）")
        return 0
    if argv[0] not in docs:
        print(f"没有 {argv[0]}；能查的：{', '.join(docs)}", file=sys.stderr)
        return 1
    print(show(docs[argv[0]]))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
