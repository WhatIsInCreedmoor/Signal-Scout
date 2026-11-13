# NGINX Reverse Proxy Configuration for Signal Scout

This guide details configuring an NGINX reverse proxy in front of the Signal Scout Django application, providing SSL termination, PWA asset delivery, and Gunicorn worker protection.

---

## 1. Prerequisites on the NGINX Proxy

### A. Deploy PWA Assets
Place the Progressive Web App (PWA) assets in `/var/www/signalscout/`:
```bash
sudo mkdir -p /var/www/signalscout
# Copy assets from signalscout repository (or deployment folder):
sudo cp favicon.ico icon-192.png icon-512.png manifest.json sw.js /var/www/signalscout/

# Set ownership and readable permissions
sudo chown -R www-data:www-data /var/www/signalscout
sudo chmod 755 /var/www/signalscout
sudo chmod 644 /var/www/signalscout/*
```

### B. Admin Basic Auth (Optional)
If using HTTP Basic Auth in front of `/admin/`:
```bash
sudo apt install apache2-utils -y
sudo htpasswd -c /etc/nginx/.signalscout.htpasswd <admin_username>
```

### C. Diffie-Hellman Parameters (If needed)
If not already generated on the proxy:
```bash
sudo openssl dhparam -out /etc/ssl/certs/dhparam.pem 2048
```

---

## 2. NGINX Site Configuration

Create `/etc/nginx/sites-available/signalscout`:

```nginx
server {
  listen 80;
  server_name signalscout.example.org;
  return 301 https://$host$request_uri;
}

server {
  listen 443 ssl http2;
  server_name signalscout.example.org;
  ssl_certificate /etc/letsencrypt/live/signalscout.example.org/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/signalscout.example.org/privkey.pem;
  ssl_dhparam /etc/ssl/certs/dhparam.pem;
  add_header X-Frame-Options "SAMEORIGIN";
  add_header X-XSS-Protection "1; mode=block";
  add_header X-Content-Type-Options nosniff;

  access_log /var/log/nginx/signalscout.access.log;
  error_log /var/log/nginx/signalscout.error.log;

  location / {
    proxy_pass http://SERVER_IP:8000;
    proxy_http_version 1.1;
    proxy_redirect off;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host $host:443;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
    proxy_set_header X-Scheme $scheme;

    proxy_buffering on;
    proxy_request_buffering on;
  }

  location /admin/ {
    auth_basic "Admin";
    auth_basic_user_file /etc/nginx/.signalscout.htpasswd;
    proxy_pass http://SERVER_IP:8000;
    proxy_http_version 1.1;
    proxy_redirect off;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host $host:443;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
    proxy_set_header X-Scheme $scheme;

    proxy_buffering on;
    proxy_request_buffering on;
  }

  location /.well-known/ {
    allow all;
    root /var/www/html;
  }

  location /robots.txt {
    return 200 "User-agent: *\nDisallow: /\n";
  }

  location = /favicon.ico {
    expires 1w;
    alias /var/www/signalscout/favicon.ico;
  }

  location = /icon-192.png {
    alias /var/www/signalscout/icon-192.png;
  }

  location = /icon-512.png {
    alias /var/www/signalscout/icon-512.png;
  }

  location = /manifest.json {
    alias /var/www/signalscout/manifest.json;
  }

  location = /sw.js {
    alias /var/www/signalscout/sw.js;
    add_header Cache-Control "no-cache";
  }
}
```

> **Note:** Replace `signalscout.example.org` with your domain and `DJANGO_SERVER_IP` with the private IP of your Django server (e.g. `10.10.245.45`).

---

## 3. Enable and Reload NGINX

```bash
sudo ln -sf /etc/nginx/sites-available/signalscout /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 4. Key Architectural Notes

* **`proxy_buffering on;`**: Critical when serving low-power devices. When an ESP32 downloads a ~1.7 MB OTA firmware update, Nginx buffers the file in memory from Gunicorn within milliseconds, freeing Gunicorn's synchronous workers to continue handling telemetry.
* **PWA Requirement**: The Web App Manifest specification requires both `icon-192.png` (app launcher) and `icon-512.png` (splash screen) for Chrome/Android install prompts.
* **`sw.js` Cache Header**: The service worker **must** have `Cache-Control: "no-cache"` so browser clients detect application and worker updates immediately.
* **Client IP Preservation**: `X-Real-IP` and `X-Forwarded-For` ensure Django logs and security checks register the watcher's true public IP instead of the internal reverse proxy IP.
