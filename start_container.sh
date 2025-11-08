#!/bin/bash
docker run -d --name BiometriX_Server --restart unless-stopped -p 5000:5000 -v /mnt/user/appdata/BiometriX_Server:/app -e TZ="America/New_York" python:3.11 bash -c "apt-get update && apt-get install -y git build-essential && pip install --no-cache-dir -r /app/requirements.txt && python -m uvicorn app.main:app --host 0.0.0.0 --port 5000"
