# Bifrost LAN HTTPS (mkcert / private CA)

## What this is

Traefik `websecure` (:443 on VIP `192.168.10.100`) terminates TLS for:

- `https://trader.bifrost.lan` / `stg.trader` / `dev.trader`
- `https://ops.bifrost.lan` / `stg.ops`

Certificate is minted with **mkcert** and installed as Traefik **default** `TLSStore` (`kube-system/bifrost-lan-tls`).

## Operator: issue / rotate cert

```bash
cd bifrost-trade-infra
./scripts/k3s/issue-bifrost-lan-tls.sh
```

This:

1. Ensures a local mkcert CA (`mkcert -install` on the operator Mac)
2. Writes leaf cert+key under `k8s/system/tls/` (gitignored except root CA)
3. Exports `bifrost-lan-rootCA.pem` (safe to commit / share)
4. Applies Secret + `traefik-tlsstore.yaml`

Also apply HTTP→HTTPS redirect (once):

```bash
kubectl apply -f k8s/system/traefik-trade-nodeports.yaml
```

## Clients: trust the CA (once per device)

Without this step browsers show a warning (HTTPS still works with "Advanced → proceed").

### macOS

1. Open `k8s/system/tls/bifrost-lan-rootCA.pem`
2. Keychain Access → **System** keychain → find "mkcert …"
3. Double-click → Trust → **When using this certificate: Always Trust**

Or:

```bash
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain \
  k8s/system/tls/bifrost-lan-rootCA.pem
```

### Windows 11

```bat
certutil -addstore -f Root bifrost-lan-rootCA.pem
```

(Run as Administrator; file from this directory or USB copy.)

## Smoke

```bash
curl -I https://stg.trader.bifrost.lan/api/monitor/status
curl -I https://stg.ops.bifrost.lan/
# HTTP :80 should 301/308 → https
curl -I http://stg.trader.bifrost.lan/
```

NodePort escapes (`:30880` / `:30882`) remain HTTP-only by design.
