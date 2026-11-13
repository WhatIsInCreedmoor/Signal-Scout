# Signal Scout

## ESP32 based signals Electronic Intelligence (ELINT) with a Django web API and backend.

Watch the watchers.

## Features
*   **Dynamic Mapping:** Real-time tracking and historical breadcrumbs on an interactive Leaflet map.
*   **Geographic Session Splitting:** Automatically separates target sessions when a device moves between physical detection areas.
*   **Easy Device Deployment:** Create a deployment location, create a watcher with only an API key, flash the watcher, and the details will populate on first boot/connection

## Linux Deployment Guide
Assuming Ubuntu 24.04 LTS OS and systemd. Only thing that may need to change between environments is the python venv version.

### 1: Clone the Repository
Clone the project to your deployment directory, assumed to be /opt/.
``` bash
cd /opt/
git clone signalscout.git
cd ./signalscout/
```

### 2: Configure the Environment
Copy the .env.example to .env, create a secure key, and then edit other variables in .env.
``` bash
cp .env.example .env
sed -i "s/your_secure_random_string_here/$(openssl rand -hex 32)/g" .env
```

### 3: Set Up the Virtual Environment
``` bash
sudo apt install python3.12-venv
python3 -m venv env
source ./env/bin/activate
pip install -r requirements.txt
```

### 4: Initialize the Application
``` bash
cd ./signalscout/
python manage.py migrate
python manage.py collectstatic --noinput
```

### 5: Create a service account
``` bash
sudo useradd --system --no-create-home signalscout
sudo chown -R signalscout:www-data /opt/signalscout
```

### 6: Configure the Systemd Service
``` bash
sudo nano /etc/systemd/system/signalscout.service
```

``` bash
[Unit]
Description=Gunicorn daemon for signalscout
After=network.target

[Service]
User=signalscout
Group=www-data
WorkingDirectory=/opt/signalscout/signalscout
ExecStart=/opt/signalscout/env/bin/gunicorn --workers 3 --bind 0.0.0.0:8000 signalscout.wsgi:application
ExecReload=/bin/kill -HUP $MAINPID

[Install]
WantedBy=multi-user.target
```

### 7: Start and Enable the Service
```bash
sudo systemctl daemon-reload
sudo systemctl start signalscout
sudo systemctl enable signalscout
```

## Documentation
* [NGINX Reverse Proxy Configuration](nginx/nginx.md)
