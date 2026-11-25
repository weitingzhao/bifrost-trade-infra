"""rewrite_refs: citations of absorbed material point at the absorbing law.

Origin: 2026-11-24, Owner: once the new laws cover the 69 rows of material,
every citation in code and documents points at the new law before the
material is archived.
"""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location("rewrite_refs", pathlib.Path(__file__).with_name("rewrite_refs.py"))
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)

LAWS = [
    {"law": "28", "op": "transcribed", "status": "已落"},
    {"law": "50", "op": "transcribed", "status": "未落"},
    {"law": "90", "op": "add", "status": "已批", "frame": {"level": 2, "absorbs": ["28"]}},
    {"law": "91", "op": "add", "status": "已批", "frame": {"level": 2, "absorbs": ["28", "50"]}},
]


def test_citations_follow_the_absorbing_law():
    amap = rr.absorbed_map(LAWS)
    assert amap == {"28": 90, "50": 91}
    text, n = rr.rewrite("see law 28 and 法 50; OWNER_LAW #28; Law 28.", amap, {"28", "50"})
    assert (text, n) == ("see law 90 and 法 91; OWNER_LAW #90; Law 90.", 4)


def test_what_is_not_absorbed_material_stays():
    # The positive control's other side: a law in force, an unabsorbed row
    # and a word ending in 法 are left as they are.
    amap = rr.absorbed_map(LAWS)
    text, n = rr.rewrite("law 90, law 12, 合法 28", amap, {"28", "50", "12"})
    assert (text, n) == ("law 90, law 12, 合法 28", 0)


def test_laws_in_force_are_written_as_their_code():
    # Origin: 决定 2026-11-25 (LAW-1 一: laws are cited by code, no abbreviations). A citation
    # of a law in force by number becomes LAW-k, prefix and all; material and
    # other numbers stay (the positive control's other side).
    codes = {"86": "LAW-1", "89": "CORE-1", "91": "LAW-6", "95": "LAW-10", "98": "LAW-13", "99": "DAO-1"}
    text, n = rr.to_codes("law 95 and 法 91; OWNER_LAW #86; Law 98 s1; law 28; 法 89; law 99", codes)
    assert (text, n) == ("LAW-10 and LAW-6; LAW-1; LAW-13 s1; law 28; CORE-1; DAO-1", 6)
