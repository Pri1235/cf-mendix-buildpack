#!/bin/bash
# Test script to verify sidecar hybrid approach setup

echo "==================================================="
echo "HANA Sidecar - Hybrid Approach Verification"
echo "==================================================="
echo ""

APP_NAME="$1"

if [ -z "$APP_NAME" ]; then
    echo "Usage: $0 <app-name>"
    echo "Example: $0 my-mendix-app"
    exit 1
fi

echo "Checking app: $APP_NAME"
echo ""

# Check if app exists
echo "1. Checking if app exists..."
cf app "$APP_NAME" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "   ❌ App not found: $APP_NAME"
    exit 1
fi
echo "   ✅ App exists"
echo ""

# Check environment variables
echo "2. Checking environment variables..."
USE_CF_SIDECAR=$(cf env "$APP_NAME" | grep "USE_CF_MANIFEST_SIDECAR" | awk '{print $2}')
ENABLE_HANA=$(cf env "$APP_NAME" | grep "ENABLE_HANA_SIDECAR" | awk '{print $2}')

echo "   USE_CF_MANIFEST_SIDECAR: $USE_CF_SIDECAR"
echo "   ENABLE_HANA_SIDECAR: $ENABLE_HANA"

if [ "$USE_CF_SIDECAR" == "true" ]; then
    echo "   ✅ Hybrid mode enabled"
else
    echo "   ⚠️  Hybrid mode not enabled (using traditional approach)"
fi
echo ""

# Check if sidecar files exist
echo "3. Checking sidecar files..."
SIDECAR_CHECK=$(cf ssh "$APP_NAME" -c "ls -la /home/vcap/app/metering/ 2>/dev/null")
if [ $? -eq 0 ]; then
    echo "   ✅ Sidecar directory exists"
    echo ""
    echo "   Files in /home/vcap/app/metering/:"
    echo "$SIDECAR_CHECK" | awk '{print "      " $0}'
    
    # Check for required files
    echo ""
    echo "   Checking required files..."
    echo "$SIDECAR_CHECK" | grep -q "sidecar.py" && echo "      ✅ sidecar.py" || echo "      ❌ sidecar.py missing"
    echo "$SIDECAR_CHECK" | grep -q "vendor" && echo "      ✅ vendor/" || echo "      ❌ vendor/ missing"
    
else
    echo "   ❌ Sidecar directory not found"
fi
echo ""

# Check running processes
echo "4. Checking running processes..."
PROCESSES=$(cf ssh "$APP_NAME" -c "ps aux | grep -E 'sidecar|python' | grep -v grep")
if [ -n "$PROCESSES" ]; then
    echo "   Python/Sidecar processes:"
    echo "$PROCESSES" | awk '{print "      " $0}'
else
    echo "   ⚠️  No sidecar processes found"
fi
echo ""

# Check app processes (including sidecars)
echo "5. Checking CF app processes..."
cf app "$APP_NAME" | grep -A 10 "type:"
echo ""

# Check recent logs
echo "6. Checking recent logs for sidecar activity..."
LOGS=$(cf logs "$APP_NAME" --recent | grep -i sidecar | tail -5)
if [ -n "$LOGS" ]; then
    echo "   Recent sidecar log entries:"
    echo "$LOGS" | awk '{print "      " $0}'
else
    echo "   ⚠️  No sidecar logs found in recent logs"
fi
echo ""

echo "==================================================="
echo "Verification complete!"
echo "==================================================="
echo ""
echo "Next steps:"
echo "  - View all logs: cf logs $APP_NAME"
echo "  - SSH to app: cf ssh $APP_NAME"
echo "  - Check processes: cf ssh $APP_NAME -c 'ps aux | grep python'"
