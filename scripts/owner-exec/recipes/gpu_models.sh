# recipe gpu-models (host tier, gpu-server only, READ-ONLY): model files on disk, launch profiles, disk room.
set -eu
[ "$(hostname -s)" = ubt-ai-4090 ]
M=/home/vision/gpu-lab/strata-20261101/models
find $M -maxdepth 3 -name '*.gguf' -printf '%s %p\n' 2>/dev/null | awk '{printf "%.1fG %s\n",$1/1e9,$2}' | sed "s|$M/||" | head -20
ls /home/vision/.local/state/strata/launch/ | grep -E '\.json$' | grep -v choices
df -h $M | awk 'NR==2{print "disk:", $3, "used of", $2, "free", $4}'
echo RECIPE=gpu-models DONE
