# Hosting on Oracle Cloud "Always Free" (staging)

A free server for a staging copy of Fairpaper (the app, the API and the database) with HTTPS, so the landing page on Netlify can save waitlist sign-ups. It is far smaller than production: use it to try the app and collect sign-ups, not to prove the 500-candidate load targets.

Free limits change; check Oracle's current "Always Free" page before you rely on them. Today they include Arm (Ampere A1) servers with up to 4 CPUs and 24 GB of memory in total, and 200 GB of disk.

## 1. Create the account (you)

1. Go to oracle.com/cloud/free and choose **Start for free**.
2. **Home region:** pick **India West (Mumbai)** or **Singapore**, closest to Bangladesh. You can't change it later, and free Arm servers run only in the home region.
3. Oracle asks for a card to check your identity. Free resources aren't charged.
4. *Optional, later:* upgrading to **Pay As You Go** keeps everything free within the limits. It makes it less likely Oracle reclaims an idle free server or reports "out of capacity". Set a budget alert at 1 USD if you do.

## 2. Create the server

1. Go to **Compute → Instances → Create instance**.
2. Choose these settings:
   - **Image:** Canonical Ubuntu 24.04.
   - **Shape:** Ampere, **VM.Standard.A1.Flex**, 2 OCPUs, 12 GB memory.
   - **Networking:** the default VCN, with a public IPv4 address.
   - **SSH keys:** choose **Generate a key pair for me**, then download the private key and keep it safe.
3. Choose **Create**.
4. If it says "Out of capacity", try another availability domain, or try again later. Arm capacity frees up during the day.
5. Note the server's **public IP address**.

## 3. Open ports 80 and 443

The cloud firewall and the server's own firewall both block web traffic until you open it.

1. In the cloud, go to **Networking → Virtual cloud networks → your VCN → Security Lists → Default**.
2. Add two ingress rules:
   - source `0.0.0.0/0`, TCP, port **80**;
   - source `0.0.0.0/0`, TCP, port **443**.
3. Don't open 3000 or 8000.
4. On the server, run step 4's commands. They also open 80 and 443 there.

## 4. Install Docker and start Fairpaper

Connect from your PC. On Windows, use PowerShell:

```bash
ssh -i path\to\private.key ubuntu@YOUR_SERVER_IP
```

Then run these on the server:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && exit
```

Connect again, so the Docker group takes effect.

## 5. Free web addresses (DuckDNS)

HTTPS needs a name, not just an IP address.

1. Sign in at duckdns.org.
2. Create two subdomains, for example `fairpaper-api` and `fairpaper-app`.
3. Point both at the server's IP.
4. When you buy a real domain later, change `API_DOMAIN` and `APP_DOMAIN` (step 6) and restart. Caddy fetches new certificates by itself.

## 6. Configure and run

```bash
git clone https://github.com/twsf-strugg1es/Fairpaper-exam-management-system.git fairpaper
cd fairpaper
cp deploy/.env.example deploy/.env
nano deploy/.env
```

In `deploy/.env`, fill in:
- **The two domains:** `API_DOMAIN` and `APP_DOMAIN`.
- **`CORS_ORIGINS`:** the app's address and the Netlify site's address.
- **`SECRET_KEY`:** at least 32 characters. Generate one with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
- **`POSTGRES_PASSWORD`:** a strong password.
- **The Sentry settings:** `SENTRY_DSN_API`, `SENTRY_DSN_WEB` and `SENTRY_ORIGIN`.

Then start it:

```bash
docker compose --env-file deploy/.env -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
docker compose --env-file deploy/.env -f docker-compose.yml -f deploy/docker-compose.prod.yml exec api python create_admin.py
```

`create_admin.py` creates the first owner and prints a password once; store it in your password manager.

Check `https://fairpaper-api.duckdns.org/health`. It answers `{"status": "ok"}` once Caddy has its certificate, usually within a minute.

## 7. Updates and backups

**Update to the latest code:**

```bash
git pull
docker compose --env-file deploy/.env -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
```

Migrations run when the API starts.

**Daily backup:** add this cron line (`crontab -e`). It keeps 14 days.

```bash
0 3 * * * cd ~/fairpaper && docker compose exec -T db pg_dump -U fairpaper online_exam_system | gzip > ~/backup-$(date +\%F).sql.gz && find ~ -name 'backup-*.sql.gz' -mtime +14 -delete
```

**Email:** emails go to the server's log (`EMAIL_BACKEND=console`) until you choose a provider (task 2.3).
