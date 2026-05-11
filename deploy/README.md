# Deploy

## Routine deploys

Just `git push` to `derive-not-detect` or `main`. GitHub Actions handles
the rest — see `.github/workflows/deploy.yml`. No SSH required.

## If CI fails

1. View logs: https://github.com/J110/GerokSports/actions
2. Manual emergency override (console SSH from GCP web UI):
   ```
   cd /mnt/data/sportscomm
   bash deploy/deploy.sh
   ```
3. Standalone health check:
   ```
   bash deploy/healthcheck.sh
   ```

## First-time VM bootstrap

```
cd /mnt/data/sportscomm
git clone https://github.com/J110/GerokSports.git .
git checkout derive-not-detect
sudo mkdir -p /etc/sportscomm
sudo cp deploy/secrets.env.example /etc/sportscomm/secrets.env
sudo chmod 0600 /etc/sportscomm/secrets.env
# Fill in real keys: sudo nano /etc/sportscomm/secrets.env
bash deploy/deploy.sh
```

## GitHub Actions one-time setup

1. GCP Console → IAM → Service Accounts → create `qrackpot-github-actions`
2. Grant roles: `roles/compute.osAdminLogin`, `roles/iap.tunnelResourceAccessor`
3. Generate JSON key, download
4. GitHub repo → Settings → Secrets → Actions → add `GCP_SA_KEY` = paste JSON

## Service controls (on VM, manual override only)

```
sudo systemctl status ui.service
sudo systemctl restart ui.service
sudo journalctl -u ui.service -f

sudo systemctl status caddy
sudo journalctl -u caddy -f
```

## Pipeline service

`pipeline.service` is installed but disabled by default. Enable once SRT
ingest is wired (Phase 1):

```
sudo systemctl enable pipeline.service
sudo systemctl start pipeline.service
```
