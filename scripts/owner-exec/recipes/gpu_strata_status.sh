# recipe gpu-strata-status (host tier, gpu-server only, READ-ONLY: writes nothing, restarts nothing)
# Law 85 (2026-11-24): a read-only card runs as a recipe, no Owner code. Prints what 11-24's cards
# #718/#720/#730/#734/#739 had to read one at a time, compact enough for the 1700-byte output tail.
set -eu
[ "$(hostname -s)" = ubt-ai-4090 ]
L=/home/vision/.local/state/strata/launch
for u in bifrost-strata-iq3.service bifrost-strata-lan.socket bifrost-harness-gateway.service bifrost-harness-native.service; do
  printf '%s %s %s\n' "$u" "$(systemctl is-active $u 2>/dev/null)" "$(systemctl is-enabled $u 2>/dev/null)"
done
ls /etc/systemd/system/bifrost-strata-iq3.service.d/ 2>/dev/null | sed 's/^/drop-in: /' || true
curl -s -m 5 http://127.0.0.1:8082/props | python3 -c 'import json,sys
try:
  j=json.load(sys.stdin); print("props: n_ctx", j.get("n_ctx"), "slots", j.get("total_slots"), "model", j.get("model_alias"))
except Exception: print("props: no answer on 127.0.0.1:8082")'
ss -Hltn "( sport = :8080 or sport = :8082 )" | awk '{print "listen:", $4}'
echo "gpu: $(nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader)"
free -g | awk 'NR==2{print "mem GiB: total",$2,"used",$3,"cache",$6,"avail",$7}'
for p in iq3_s-32k ud-q4_k_xl-32k; do
  python3 -c 'import json,sys
j=json.load(open(sys.argv[1])); a=j.get("args",[])
c=a[a.index("--max-context")+1] if "--max-context" in a else "?"
print("profile", sys.argv[2], "ctx", c, "port", j.get("port"), "model", j.get("model_name"))' "$L/$p.json" "$p" 2>/dev/null || true
done
journalctl -u bifrost-strata-iq3.service -n 3 --no-pager 2>&1 | cut -c1-150
echo RECIPE=gpu-strata-status DONE
