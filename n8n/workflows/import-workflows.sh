#!/bin/sh

echo "Starting custom import script..."

for f in /files/*.json; do
    if [ -f "$f" ]; then
        echo "Found workflow file: $f"
        echo "Importing $f..."
        n8n import:workflow --input="$f"
        
        # Extract ID to activate it
        # We use grep to find the id field, and cut to extract the value
        # Pattern matches: "id": "value"
        ID=$(grep -o '"id": "[^"]*"' "$f" | head -n 1 | cut -d'"' -f4)
        
        if [ -n "$ID" ]; then
            echo "Activating workflow ID: $ID"
            n8n update:workflow --id="$ID" --active=true
        else
            echo "Could not find workflow ID in $f"
        fi
    fi
done

echo "Starting n8n..."
/docker-entrypoint.sh
