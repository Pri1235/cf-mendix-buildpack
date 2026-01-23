# HANA Sidecar - Hybrid Deployment Approach

This document explains the hybrid approach for deploying the HANA sidecar, where the buildpack stages the sidecar files but Cloud Foundry's native sidecar feature starts and manages the process.

## Overview

### Traditional Approach (Default)
- Buildpack copies sidecar files during staging
- Buildpack starts sidecar as a subprocess during app startup
- Sidecar runs as a child process of the main app

### Hybrid Approach (New)
- Buildpack copies sidecar files during staging ✓
- Cloud Foundry starts sidecar as a separate process via manifest
- Better process isolation and management by CF platform

## Benefits of Hybrid Approach

1. **Better Process Management**: CF platform manages the sidecar lifecycle
2. **Process Isolation**: Sidecar runs as independent process, not child of app
3. **Resource Control**: Separate memory limits for sidecar
4. **Crash Recovery**: CF can independently restart failed sidecars
5. **Monitoring**: Separate health checks and metrics per process
6. **Cleaner Logs**: Separate log streams for main app and sidecar

## Setup Instructions

### 1. Enable Hybrid Mode

Set the environment variable in your `manifest.yml`:

```yaml
env:
  USE_CF_MANIFEST_SIDECAR: "true"
  ENABLE_HANA_SIDECAR: "true"  # Required to stage the files
```

### 2. Define Sidecar in Manifest

Add the sidecar definition to your `manifest.yml`:

```yaml
sidecars:
  - name: hana-sidecar
    command: python3 /home/vcap/app/metering/sidecar.py
    process_types: ['web']
    memory: 256M
```

### 3. Complete Manifest Example

See [manifest-with-sidecar.yml](./manifest-with-sidecar.yml) for a complete example.

## How It Works

### Staging Phase (cf push)

1. Cloud Foundry runs the buildpack during staging
2. Buildpack detects `ENABLE_HANA_SIDECAR=true`
3. Buildpack copies sidecar files from `lib/hana-sidecar/` to `/home/vcap/app/metering/`
4. Buildpack copies vendor dependencies (HANA client libraries)
5. Buildpack makes `sidecar.py` executable
6. Droplet is created with all files

### Runtime Phase (app start)

**With USE_CF_MANIFEST_SIDECAR=true:**
1. CF starts the main web process (Mendix app)
2. Buildpack's `metering.run()` detects hybrid mode and skips starting sidecar
3. CF separately starts the sidecar process defined in manifest
4. Both processes run independently under CF supervision

**With USE_CF_MANIFEST_SIDECAR=false (default):**
1. CF starts the main web process (Mendix app)
2. Buildpack's `metering.run()` starts sidecar as subprocess
3. Sidecar runs as child process of the main app

## File Locations

After staging, the sidecar files are located at:

```
/home/vcap/app/metering/
├── sidecar.py              # Main sidecar script
├── requirements.txt        # Python dependencies
├── conf.json              # Configuration (created by buildpack)
└── vendor/                # HANA client libraries
    ├── hdbcli/
    ├── pyhdbcli.abi3.so
    └── ...
```

## Environment Variables

The sidecar receives these environment variables automatically:

- `VCAP_SERVICES` - Contains HANA service credentials
- `MXUMS_SUBSCRIPTION_SECRET` - License subscription secret (if using metering)
- `MXUMS_LICENSESERVER_URL` - License server URL (if using metering)
- `MXUMS_ENVIRONMENT_NAME` - Environment name (if using metering)
- `MXUMS_DB_CONNECTION_URL` - Database connection URL
- `MXUMS_PROJECT_ID` - Mendix project ID

## Deployment Commands

### Deploy with hybrid approach:
```bash
cf push -f manifest-with-sidecar.yml
```

### Check running processes:
```bash
cf ssh my-mendix-app -c "ps aux | grep -E 'sidecar|python'"
```

### View sidecar logs:
```bash
# All logs (includes sidecar)
cf logs my-mendix-app

# Recent logs
cf logs my-mendix-app --recent | grep sidecar
```

### Check sidecar process status:
```bash
cf app my-mendix-app
```

## Troubleshooting

### Sidecar files not found

Check if staging completed successfully:
```bash
cf ssh my-mendix-app -c "ls -la /home/vcap/app/metering/"
```

Expected output:
```
drwxr-xr-x vcap vcap metering/
-rwxr-xr-x vcap vcap sidecar.py
-rw-r--r-- vcap vcap requirements.txt
-rw-r--r-- vcap vcap conf.json
drwxr-xr-x vcap vcap vendor/
```

### Sidecar not starting

1. Check if `USE_CF_MANIFEST_SIDECAR=true`
2. Verify sidecar definition in manifest
3. Check logs: `cf logs my-mendix-app --recent`
4. Check process status: `cf app my-mendix-app`

### HANA connection issues

1. Verify HANA service is bound: `cf services`
2. Check VCAP_SERVICES: `cf env my-mendix-app`
3. Check sidecar logs for connection errors

## Migration Guide

### From Traditional to Hybrid Approach

1. Add environment variable to manifest:
   ```yaml
   env:
     USE_CF_MANIFEST_SIDECAR: "true"
   ```

2. Add sidecar definition to manifest:
   ```yaml
   sidecars:
     - name: hana-sidecar
       command: python3 /home/vcap/app/metering/sidecar.py
       process_types: ['web']
       memory: 256M
   ```

3. Redeploy: `cf push`

### Rollback to Traditional Approach

1. Remove or set to false:
   ```yaml
   env:
     USE_CF_MANIFEST_SIDECAR: "false"
   ```

2. Remove sidecar definition from manifest

3. Redeploy: `cf push`

## Technical Details

### Buildpack Changes

Modified file: `buildpack/telemetry/metering.py`

Key changes:
- Added `USE_CF_MANIFEST_SIDECAR` environment variable check
- Modified `run()` function to skip starting subprocess when hybrid mode is enabled
- Staging phase (`stage()`) remains unchanged - files are always copied if enabled

### Code Logic

```python
# In metering.py
USE_CF_MANIFEST_SIDECAR = os.environ.get("USE_CF_MANIFEST_SIDECAR", "false").lower() == "true"

def run():
    if USE_CF_MANIFEST_SIDECAR:
        # Skip starting sidecar - let CF manifest handle it
        logging.info("USE_CF_MANIFEST_SIDECAR is enabled")
        logging.info("Sidecar files ready at /home/vcap/app/metering/")
        return
    
    # Traditional approach: start sidecar as subprocess
    # ... existing code ...
```

## Support and Contact

For issues or questions:
- Check buildpack logs during staging
- Review CF logs during runtime
- Verify environment variables and manifest configuration

---

**Note**: Both traditional and hybrid approaches are supported. Choose based on your operational requirements and CF platform capabilities.
