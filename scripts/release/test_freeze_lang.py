"""The 678 cases and an independent recogniser written from the productions."""

from __future__ import annotations

import itertools
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import freeze_gate as fg

_W = r"[ \t\r\n]*"


def _q(s: str) -> str:
    return '"' + re.escape(s) + '"'


def _oracle_pattern() -> str:
    rv = _q("resourceVersion") + _W + ":" + _W + '"' + r"[0-9]{1,32}" + '"'
    ct = _q("continue") + _W + ":" + _W + '""'
    meta = r"\{" + _W + "(?:" + rv + _W + r"\}|" + ct + _W + "," + _W + rv + _W + r"\}|" + rv + _W + "," + _W + ct + _W + r"\})"
    av = _W + _q("apiVersion") + _W + ":" + _W + _q("release.bifrost.io/v1")
    kd = _W + _q("kind") + _W + ":" + _W + _q("FreezeList")
    it = _W + _q("items") + _W + ":" + _W + r"\[" + _W + r"\]"
    md = _W + _q("metadata") + _W + ":" + _W + meta
    members = [av, kd, md, it]
    alts = []
    for perm in itertools.permutations(range(4)):
        alts.append(
            r"\{" + members[perm[0]] + _W + "," + members[perm[1]] + _W + ","
            + members[perm[2]] + _W + "," + members[perm[3]] + _W + r"\}"
        )
    return r"\A" + _W + "(?:" + "|".join(alts) + ")" + _W


_ORACLE = re.compile(_oracle_pattern().encode("ascii"))


def oracle_match(body: bytes) -> bool:
    found = _ORACLE.match(body)
    return found is not None and found.end() == len(body)


def _permute(n: int) -> list[list[int]]:
    return [list(p) for p in itertools.permutations(range(n))]


def _repeat(c: int, n: int) -> bytes:
    return bytes([c]) * n


def _compact(perm: list[int], form: int, digits: int) -> bytes:
    rv = "1" * digits
    r = '"resourceVersion":"' + rv + '"'
    c = '"continue":""'
    if form == 0:
        meta = "{" + r + "}"
    elif form == 1:
        meta = "{" + c + "," + r + "}"
    else:
        meta = "{" + r + "," + c + "}"
    parts = [
        '"apiVersion":"release.bifrost.io/v1"',
        '"kind":"FreezeList"',
        '"metadata":' + meta,
        '"items":[]',
    ]
    return ("{" + parts[perm[0]] + "," + parts[perm[1]] + "," + parts[perm[2]] + "," + parts[perm[3]] + "}").encode()


def _skeleton(digits: str = "1") -> tuple[bytes, list[int]]:
    buf = bytearray()
    marks: list[int] = []

    def w() -> None:
        marks.append(len(buf))

    def s(x: str) -> None:
        buf.extend(x.encode())

    def q(x: str) -> None:
        s('"' + x + '"')

    def m_av() -> None:
        w(); q("apiVersion"); w(); s(":"); w(); q("release.bifrost.io/v1")

    def m_it() -> None:
        w(); q("items"); w(); s(":"); w(); s("["); w(); s("]")

    def m_kd() -> None:
        w(); q("kind"); w(); s(":"); w(); q("FreezeList")

    def c() -> None:
        q("continue"); w(); s(":"); w(); q("")

    def r() -> None:
        q("resourceVersion"); w(); s(":"); w(); q(digits)

    def meta() -> None:
        s("{"); w(); c(); w(); s(","); w(); r(); w(); s("}")

    def m_md() -> None:
        w(); q("metadata"); w(); s(":"); w(); meta()

    w(); s("{"); m_av(); w(); s(","); m_it(); w(); s(","); m_kd(); w(); s(","); m_md(); w(); s("}"); w()
    return bytes(buf), marks


def _index(b: bytes, sub: bytes, start: int = 0) -> int:
    return b.find(sub, start)


def _slot_inserts(base: bytes) -> list[bytes]:
    top_end = len(base) - 1
    meta_key = b'"metadata":'
    meta_at = _index(base, meta_key)
    meta_brace = meta_at + len(meta_key)
    meta_end = top_end - 1
    meta_comma = _index(base, b",", meta_brace)
    commas = [i for i, c in enumerate(base) if c == 44 and (i < meta_brace or i > meta_end)]
    specs = [
        (1, b'"z":"",'),
        (commas[0] + 1, b'"z":"",'),
        (commas[1] + 1, b'"z":"",'),
        (commas[2] + 1, b'"z":"",'),
        (top_end, b',"z":""'),
        (meta_brace + 1, b'"z":"",'),
        (meta_comma + 1, b'"z":"",'),
        (meta_end, b',"z":""'),
    ]
    out = []
    for at, text in specs:
        out.append(base[:at] + text + base[at:])
    return out


def _digits33(base: bytes) -> bytes:
    old = b'"resourceVersion":"1"'
    neu = b'"resourceVersion":"' + _repeat(0x31, 33) + b'"'
    at = _index(base, old)
    return base[:at] + neu + base[at + len(old):]


def _slash_inserts(base: bytes) -> list[bytes]:
    ats = []
    frm = 0
    for key in (b'"apiVersion"', b'"items"', b'"kind"', b'"metadata"', b'"continue"', b'"resourceVersion"'):
        at = _index(base, key, frm)
        ats.append(at + 1)
        frm = at + len(key)
    for val in (b'"release.bifrost.io/v1"', b'"FreezeList"'):
        ats.append(_index(base, val) + 1)
    c_at = _index(base, b'"continue"')
    ats.append(_index(base, b'""', c_at) + 1)
    rv = _index(base, b'"resourceVersion"')
    ats.append(_index(base, b'"1"', rv) + 1)
    return [base[:at] + b"\\" + base[at:] for at in ats]


def _dup_keys(base: bytes) -> list[bytes]:
    out = []
    top_end = len(base) - 1
    for member in (
        b'"apiVersion":"release.bifrost.io/v1"',
        b'"items":[]',
        b'"kind":"FreezeList"',
        b'"metadata":{"continue":"","resourceVersion":"1"}',
    ):
        text = b"," + member
        out.append(base[:top_end] + text + base[top_end:])
    meta_end = top_end - 1
    for member in (b'"continue":""', b'"resourceVersion":"1"'):
        text = b"," + member
        out.append(base[:meta_end] + text + base[meta_end:])
    return out


def _random_bodies() -> list[bytes]:
    s = 310101
    total = 255 * 256 // 2
    stream = bytearray(total)
    for i in range(total):
        s = (1103515245 * s + 12345) % (1 << 31)
        stream[i] = (s >> 16) % 256
    out = []
    at = 0
    for n in range(256):
        out.append(bytes(stream[at:at + n]))
        at += n
    return out


def generate_cases() -> list[tuple[bytes, bool, str]]:
    out: list[tuple[bytes, bool, str]] = []
    for perm in _permute(4):
        for form in range(3):
            for n in (1, 32):
                out.append((_compact(perm, form, n), True, "member"))
    base, marks = _skeleton("1")
    assert len(base) == 118 and len(marks) == 27
    for at in marks:
        for c in (0x20, 0x09, 0x0A, 0x0D):
            out.append((base[:at] + bytes([c]) + base[at:], True, "member"))
    for i in range(len(base)):
        b = bytearray(base)
        b[i] = 0xFF
        out.append((bytes(b), False, "near"))
    for b in _slot_inserts(base):
        out.append((b, False, "near"))
    out.append((_digits33(base), False, "near"))
    for b in _slash_inserts(base):
        out.append((b, False, "near"))
    for b in _dup_keys(base):
        out.append((b, False, "near"))
    for at in marks:
        out.append((base[:at] + b"A" + base[at:], False, "near"))
    for b in _random_bodies():
        out.append((b, False, "random"))
    return out


_HAND = [
    ("measured", b'{"apiVersion":"release.bifrost.io/v1","items":[],"kind":"FreezeList","metadata":{"continue":"","resourceVersion":"84135567"}}\n', True),
    ("two-resourceVersion", b'{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"resourceVersion":"1","resourceVersion":"2"},"items":[]}', False),
    ("two-continue", b'{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"continue":"","continue":""},"items":[]}', False),
    ("continue-rv-continue", b'{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"continue":"","resourceVersion":"1","continue":""},"items":[]}', False),
    ("rv-continue-rv", b'{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"resourceVersion":"1","continue":"","resourceVersion":"2"},"items":[]}', False),
    ("only-continue", b'{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"continue":""},"items":[]}', False),
    ("nan", b'{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{},"items":[],"x":NaN}', False),
    ("infinity", b'{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{},"items":[],"x":Infinity}', False),
    ("remainingItemCount", b'{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"resourceVersion":"1","remainingItemCount":1},"items":[]}', False),
    ("fifth", b'{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"resourceVersion":"1"},"items":[],"z":""}', False),
    ("dup-member", b'{"apiVersion":"release.bifrost.io/v1","apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"resourceVersion":"1"}}', False),
    ("continue-nonempty", b'{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"continue":"x","resourceVersion":"1"},"items":[]}', False),
    ("digits-33", b'{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"resourceVersion":"111111111111111111111111111111111"},"items":[]}', False),
    ("digits-0", b'{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"resourceVersion":""},"items":[]}', False),
    ("trailing", b'{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"resourceVersion":"1"},"items":[]}A', False),
]


class LangTests(unittest.TestCase):
    def test_generated(self) -> None:
        cases = generate_cases()
        self.assertEqual(len(cases), 678)
        members = near = random = accept = 0
        for body, member, group in cases:
            if group == "member":
                members += 1
            elif group == "near":
                near += 1
            else:
                random += 1
            got = fg.member_of_l(body)
            ora = oracle_match(body)
            self.assertEqual(got, ora, group)
            self.assertEqual(got, member, group)
            clear = fg.decide_http(200, body).verdict == "clear"
            self.assertEqual(clear, got)
            if got:
                accept += 1
        self.assertEqual((members, near, random, accept), (252, 170, 256, 252))
        print(f"cases {len(cases)}")
        print(f"members {members}")
        print(f"near {near}")
        print(f"random {random}")
        print("seed 310101")

    def test_hand(self) -> None:
        for name, body, member in _HAND:
            self.assertEqual(fg.member_of_l(body), member, name)
            self.assertEqual(oracle_match(body), member, name)
            clear = fg.decide_http(200, body).verdict == "clear"
            self.assertEqual(clear, member, name)

    def test_status_is_not_a_list(self) -> None:
        body = _HAND[0][1]
        for status in (404, 403, 500):
            self.assertNotEqual(fg.decide_http(status, body).verdict, "clear", status)


if __name__ == "__main__":
    unittest.main()
