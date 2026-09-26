#!/usr/bin/env python3
"""Which registry tags are worth keeping, and what they actually weigh.

The keep rule is deliberately conservative: a tag stays if **anything on the
cluster references it** (deploy / sts / ds / cronjob / job), plus the newest few
semver tags per repo and the moving tags (prod / stg / dev / latest / main).
Measured 2026-09-26: 49 of 398 tags, 5.30 GB of 112.9 GB. Blobs are deduplicated
by digest, so that is real bytes and not the sum of image sizes.

**Do not replace the reference scan with "keep the newest N."** Measured the same
day: `research-harness` runs daily and each run pins a *different* historical
version (0.105.4, 0.106.0, 0.113.0 on successive days), because another session
is repairing history one release at a time. Tags that look old are in active use,
and a newest-N rule would have deleted images somebody was running.

Used by docs/REGISTRY_PERSISTENCE_PLAN.md step 1, and meant to become the weekly
pruner step 8 asks for: delete everything outside the keep set by digest, then
run `registry garbage-collect` (REGISTRY_STORAGE_DELETE_ENABLED is already true).

Read-only. Needs KUBECONFIG and reachability to the registry NodePort.
"""

import json, subprocess, urllib.request, collections, re

REG = "http://192.168.10.73:30500"
ACCEPT = ", ".join([
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.oci.image.index.v1+json",
])

def get(path, accept=None):
    req = urllib.request.Request(REG + path)
    if accept: req.add_header("Accept", accept)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read()), dict(r.headers)

REFERENCED = set()
out = subprocess.run(["kubectl","get","deploy,sts,ds,cronjob,job","-A","-o","json"],
                     capture_output=True, text=True).stdout
for it in json.loads(out)["items"]:
    sp = (it["spec"].get("template",{}).get("spec")
          or it["spec"].get("jobTemplate",{}).get("spec",{}).get("template",{}).get("spec") or {})
    for c in (sp.get("containers") or []) + (sp.get("initContainers") or []):
        img = c.get("image","")
        if "30500" in img and ":" in img:
            repo, tag = img.rsplit(":",1)
            REFERENCED.add((repo.split("/")[-1], tag))

repos = get("/v2/_catalog")[0]["repositories"]
MOVING = {"prod","stg","dev","latest","main"}
KEEP_RECENT = 3

def semver_key(t):
    parts = re.findall(r"\d+", t)
    return [int(x) for x in parts] if parts else [-1]

keep, drop_n = collections.defaultdict(set), 0
for repo in repos:
    try: tags = get(f"/v2/{repo}/tags/list")[0].get("tags") or []
    except Exception: tags = []
    if not tags: continue
    for t in tags:
        if t in MOVING: keep[repo].add(t)
    for r,t in REFERENCED:
        if r == repo and t in tags: keep[repo].add(t)
    sem = sorted([t for t in tags if t[0].isdigit()], key=semver_key)
    for t in sem[-KEEP_RECENT:]: keep[repo].add(t)
    drop_n += len(tags) - len(keep[repo])

blobs, per_repo = {}, {}
for repo, tags in keep.items():
    tot = 0
    for t in sorted(tags):
        try: m, _ = get(f"/v2/{repo}/manifests/{t}", ACCEPT)
        except Exception: continue
        mans = m.get("manifests") or [m]
        for mm in mans:
            if "layers" not in mm:
                try: mm, _ = get(f"/v2/{repo}/manifests/{mm['digest']}", ACCEPT)
                except Exception: continue
            for l in (mm.get("layers") or []) + ([mm["config"]] if mm.get("config") else []):
                blobs[l["digest"]] = l.get("size", 0)
        tot += 1
    per_repo[repo] = (tot, len(tags))

print("=== 保留清单（被引用 + 各 repo 最近 %d 个 + 移动 tag）===" % KEEP_RECENT)
for repo in sorted(keep):
    all_t = len(get(f"/v2/{repo}/tags/list")[0].get("tags") or [])
    print("  %-28s 保留 %2d / 共 %3d   %s" % (repo, len(keep[repo]), all_t,
          ",".join(sorted(keep[repo], key=lambda x:(x in MOVING, semver_key(x)))[:8])))
print()
print("  保留 tag 合计: %d   丢弃: %d" % (sum(len(v) for v in keep.values()), drop_n))
print("  唯一 blob: %d 个   **合计 %.2f GB**（层已去重）" % (len(blobs), sum(blobs.values())/1e9))
json.dump({r: sorted(v) for r,v in keep.items()}, open("keepset.json","w"), indent=1)
print("  清单写入 keepset.json")
