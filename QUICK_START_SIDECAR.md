## Quick Start: CF Manifest Sidecar Approach

### Step 1: Update your manifest.yml

```yaml
applications:
  - name: my-app
    buildpack: https://github.com/your-org/cf-mendix-buildpack.git
    env:
      USE_CF_MANIFEST_SIDECAR: "true"    # Enable hybrid mode
      ENABLE_HANA_SIDECAR: "true"         # Stage sidecar files
    
    sidecars:
      - name: hana-sidecar
        command: python3 /home/vcap/app/metering/sidecar.py
        process_types: ['web']
        memory: 256M
```

### Step 2: Deploy

```bash
cf push
```

### Step 3: Verify

```bash
# Check processes
cf app my-app

# Check logs
cf logs my-app --recent | grep -i sidecar

# SSH and verify files
cf ssh my-app -c "ls -la /home/vcap/app/metering/"
```

---

## What Gets Deployed?

✅ Buildpack stages these files:
- `/home/vcap/app/metering/sidecar.py`
- `/home/vcap/app/metering/vendor/` (HANA libraries)
- `/home/vcap/app/metering/requirements.txt`
- `/home/vcap/app/metering/conf.json`

✅ CF starts sidecar as separate process (not subprocess)

❌ Buildpack does NOT start the sidecar (CF does)

---

## Key Differences

| Aspect | Traditional | Hybrid (CF Manifest) |
|--------|------------|---------------------|
| File staging | ✓ Buildpack | ✓ Buildpack |
| Process start | ✓ Buildpack subprocess | ✓ CF process |
| Process isolation | Child process | Separate process |
| Memory limit | Shared with app | Dedicated limit |
| Crash recovery | App restart needed | Independent restart |
| Log stream | Mixed with app | Can be separated |

---

## Troubleshooting

### Files not found?
```bash
cf ssh my-app -c "ls -la /home/vcap/app/metering/"
```
→ Check if `ENABLE_HANA_SIDECAR=true`

### Sidecar not starting?
```bash
cf app my-app  # Check process status
cf logs my-app --recent | grep -i sidecar
```
→ Verify sidecar definition in manifest

### Want to switch back?
Set `USE_CF_MANIFEST_SIDECAR: "false"` and remove sidecar definition from manifest
