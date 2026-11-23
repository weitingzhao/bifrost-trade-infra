#!/bin/sh
# Used inside an Owner-approved node-run on gpu-server.
set -eu
umask 077

if [ "$(/usr/bin/id -u)" -ne 0 ] || [ "$(/usr/bin/hostname -s)" != ubt-ai-4090 ]; then
  printf '%s\n' 'GPU poweroff identity enrollment refused: wrong host or execution user.' >&2
  exit 2
fi
account=bifrost-gpu-poweroff
account_home=/var/lib/bifrost-gpu-poweroff
helper=/usr/local/sbin/bifrost-gpu-poweroff
dispatcher=/usr/local/sbin/bifrost-gpu-poweroff-ssh
key=${GPU_POWEROFF_PUBLIC_KEY:?missing enrollment public key}
printf '%s\n' "$key" | /usr/bin/grep -Eq '^ssh-ed25519 [A-Za-z0-9+/=]+$'
test "$#" -eq 1 && test -r "$1"
/bin/sh -n "$1"
status=$(/usr/bin/nvidia-smi --query-gpu=name --format=csv,noheader)
if [ "$status" != 'NVIDIA GeForce RTX 4090' ]; then
  printf '%s\n' 'GPU poweroff identity enrollment refused: expected one RTX 4090.' >&2
  exit 2
fi

if ! /usr/bin/id "$account" >/dev/null 2>&1; then
  /usr/sbin/useradd --system --user-group --no-create-home --home-dir "$account_home" --shell /bin/sh "$account"
fi
record=$(/usr/bin/getent passwd "$account")
[ "$(printf '%s' "$record" | /usr/bin/cut -d: -f6,7)" = "$account_home:/bin/sh" ]
[ "$(/usr/bin/id -u "$account")" -ne 0 ]
[ "$(/usr/bin/id -Gn "$account")" = "$account" ]
[ ! -L "$account_home" ] && [ ! -L "$account_home/.ssh" ]
/usr/bin/install -d -o root -g root -m 0755 "$account_home" "$account_home/.ssh"
/usr/bin/install -o root -g root -m 0755 "$1" "$helper"

work=$(/usr/bin/mktemp -d)
trap '/usr/bin/rm -rf "$work"' EXIT
cat > "$work/dispatch" <<'SCRIPT'
#!/bin/sh
case "${SSH_ORIGINAL_COMMAND:-}" in
  check|poweroff) exec /usr/bin/sudo -n /usr/local/sbin/bifrost-gpu-poweroff "$SSH_ORIGINAL_COMMAND" ;;
  *) exit 2 ;;
esac
SCRIPT
/usr/bin/install -o root -g root -m 0755 "$work/dispatch" "$dispatcher"
printf '%s ALL=(root) NOPASSWD: %s check, %s poweroff\n' "$account" "$helper" "$helper" > "$work/sudoers"
/usr/sbin/visudo -cf "$work/sudoers" >/dev/null
/usr/bin/install -o root -g root -m 0440 "$work/sudoers" /etc/sudoers.d/bifrost-gpu-poweroff
printf 'restrict,command="%s" %s\n' "$dispatcher" "$key" > "$work/authorized_keys"
/usr/bin/install -o root -g root -m 0644 "$work/authorized_keys" "$account_home/.ssh/authorized_keys"

printf 'GPU_HOST_KEY=%s\n' "$(/usr/bin/awk '{print $1, $2}' /etc/ssh/ssh_host_ed25519_key.pub)"
if "$helper" check; then
  printf '%s\n' 'GPU_BOOTSTRAP_CHECK=idle'
else
  printf '%s\n' 'GPU_BOOTSTRAP_CHECK=busy_or_unavailable'
fi
