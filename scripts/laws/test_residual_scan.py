"""The residual scan's citation pattern.

Origin: 2026-11-24, round 1 of the laws' residual scan counted fifteen
citations of laws that do not exist; twelve were 「合法 0」 (a lawful zero) and
two 「合法 126 字节」, and 「读法 0」 in three more, words ending in 法 read as 「法 N」.
"""
import importlib.util
import pathlib
import re

spec = importlib.util.spec_from_file_location("residual_scan", pathlib.Path(__file__).with_name("residual_scan.py"))
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


def cites(text):
    return re.findall(scan.CITE, text)


def test_citations_are_found():
    # The positive control: every form the scan is for.
    assert cites("（法 46）") == ["46"]
    assert cites("按法50办") == ["50"]
    assert cites("law 85, #729") == ["85"]
    assert cites("Law 28 says") == ["28"]
    assert cites("OWNER_LAW #12") == ["12"]


def test_words_ending_in_fa_are_not_citations():
    assert cites("合法 0 保留") == []
    assert cites("合法 126 字节正文") == []
    assert cites("算法 2 和方法 3") == []
    assert cites("立法 1 轮") == []
    assert cites("两份读法 0 分歧") == []


def test_exceptions_are_read_from_the_file(tmp_path):
    f = tmp_path / "exceptions.txt"
    f.write_text("# comment\nbifrost-platform:a/b.go:46  # why\n\n")
    assert scan.exceptions(f) == {"bifrost-platform:a/b.go:46"}
    assert scan.exceptions(tmp_path / "missing.txt") == set()
