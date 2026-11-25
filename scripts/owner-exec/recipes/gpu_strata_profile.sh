# recipe gpu-strata-profile (host tier, gpu-server only, REVERSIBLE): pick the model and the context.
# Parameters (set above this text by node-run.sh, whitelisted there): MODEL in {iq3, q4}, CTX in {32768, 65536, 131072, 262144}.
# What it changes: --max-context in that model's launch profile, and the systemd drop-in that makes the Strata
# service start the Q4 profile (present for q4, absent for iq3). Before touching anything it copies both into
# a timestamped backup; if Strata does not serve the asked context within about 4 minutes, it puts the backup
# back and restarts, and says so. Undo by hand: run this recipe again with the previous MODEL and CTX.
# No data, no credentials, no network rule is touched.
set -eu
[ "$(hostname -s)" = ubt-ai-4090 ]
L=/home/vision/.local/state/strata/launch
DROP=/etc/systemd/system/bifrost-strata-iq3.service.d
case "$MODEL" in iq3) P=$L/iq3_s-32k.json;; q4) P=$L/ud-q4_k_xl-32k.json;; *) echo "bad MODEL"; exit 2;; esac
case "$CTX" in 32768|65536|131072|262144) ;; *) echo "bad CTX"; exit 2;; esac
B=/var/lib/bifrost-strata-backups/$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$B"
cp -p $L/iq3_s-32k.json $L/ud-q4_k_xl-32k.json "$B/"; [ -d "$DROP" ] && cp -pr "$DROP" "$B/dropin" || true
echo "backup: $B"
python3 - "$P" "$CTX" <<'PY'
import json,sys
p,ctx=sys.argv[1],sys.argv[2]; j=json.load(open(p)); n=0
for k in ("args","args_written"):
    a=j.get(k)
    if isinstance(a,list) and "--max-context" in a:
        a[a.index("--max-context")+1]=ctx; n+=1
assert n>=1, "no --max-context"
j["port"]=8082
json.dump(j,open(p,"w"),indent=2); print("profile", p.rsplit("/",1)[1], "ctx", ctx)
PY
chown vision:vision "$P"
if [ "$MODEL" = q4 ]; then
  cur=$(systemctl show -p ExecStart --value bifrost-strata-iq3.service | sed -n 's/.*argv\[\]=\([^;]*\);.*/\1/p' | head -1 | sed 's/launch-ud-q4_k_xl-32k/launch-iq3_s-32k/')
  mkdir -p "$DROP"; printf '[Service]\nExecStart=\nExecStart=%s\n' "$(printf '%s' "$cur" | sed 's/launch-iq3_s-32k/launch-ud-q4_k_xl-32k/')" > "$DROP/q4-ab-test.conf"
else
  rm -f "$DROP/q4-ab-test.conf"
fi
systemctl daemon-reload
systemctl restart --no-block bifrost-strata-iq3.service
ok=0
for i in $(seq 1 46); do
  sleep 5
  c=$(curl -s -m 3 http://127.0.0.1:8082/props 2>/dev/null | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("n_ctx",""))
except Exception: print("")' || true)
  [ "$c" = "$CTX" ] && { ok=1; echo "serving $MODEL ctx $CTX after ~$((i*5))s"; break; }
done
if [ "$ok" = 1 ]; then echo RECIPE=gpu-strata-profile OK; exit 0; fi
echo "not serving $CTX after ~230s: restoring $B and restarting"
cp -p "$B/iq3_s-32k.json" "$B/ud-q4_k_xl-32k.json" $L/
rm -rf "$DROP"; [ -d "$B/dropin" ] && cp -pr "$B/dropin" "$DROP" || true
systemctl daemon-reload; systemctl restart --no-block bifrost-strata-iq3.service
echo RECIPE=gpu-strata-profile ROLLED_BACK; exit 1
