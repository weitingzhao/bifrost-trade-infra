# Image Publish SOP — K3s Insecure Registry

## Context

The Bifrost K3s cluster uses an HTTP (insecure) registry at `192.168.10.73:30500`.

Docker's default `docker push` fails because it expects HTTPS. Two workarounds are documented below.

---

## Method A — skopeo (preferred)

skopeo can copy images between transports with explicit TLS control:

```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock quay.io/skopeo/stable:latest \
  copy --dest-tls-verify=false \
  docker-daemon:<local-image>:<tag> \
  docker://<registry>/<repo>:<tag>
```

**Example** (platform-api):

```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock quay.io/skopeo/stable:latest \
  copy --dest-tls-verify=false \
  docker-daemon:bifrost-platform-api:prod \
  docker://192.168.10.73:30500/bifrost-platform-api:prod
```

**Pros**: No filesystem intermediary, works from any machine with Docker access.

---

## Method B — k3s ctr import (fallback)

Export the image as a tar and import directly into each node's containerd store:

```bash
docker save <image>:<tag> -o /tmp/image.tar
for node in 192.168.10.73 192.168.10.75 192.168.10.77 192.168.10.70 192.168.10.79; do
  scp /tmp/image.tar vision@$node:/tmp/image.tar
  ssh vision@$node 'sudo k3s ctr images import /tmp/image.tar && rm -f /tmp/image.tar'
done
```

**Pros**: Works even if the registry is down. No network pull at Pod scheduling time.

**Cons**: Must repeat for every node; image is not served by the registry for future pod scheduling on new nodes.

---

## ArgoCD Interaction

If ArgoCD auto-sync is active and the Deployment uses `imagePullPolicy: Always` with a mutable tag (e.g. `:prod`), Argo may revert the running image before the registry is updated.

### Strategy

1. **Push to registry first (Method A)** so Argo pulls the correct image on next sync — preferred.

2. **Temporarily suspend auto-sync** if you need to coordinate multi-step changes:

```bash
# Suspend
kubectl -n cicd patch app <name> --type=json \
  -p='[{"op":"remove","path":"/spec/syncPolicy/automated"}]'

# ... perform deploy / image push ...

# Re-enable
kubectl -n cicd patch app <name> --type=merge -p '{
  "spec": {
    "syncPolicy": {
      "automated": {"prune": true, "selfHeal": true},
      "syncOptions": ["CreateNamespace=true"]
    }
  }
}'
```

---

## Verification

After deploy, verify the running binary hash matches what was built locally:

```bash
POD=$(kubectl -n <ns> get pods -l app.kubernetes.io/name=<name> -o jsonpath='{.items[0].metadata.name}')
kubectl -n <ns> debug -q "$POD" --image=busybox:1.36 --target=<container> --profile=general -- \
  sh -c 'sha256sum /proc/1/root/usr/local/bin/<binary>'
```

Compare with the local build output:

```bash
sha256sum bin/platform-api-linux-amd64
```

If hashes match, the correct binary is running in the cluster.
