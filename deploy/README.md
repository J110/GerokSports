# Deploy

## First-time bootstrap (on VM)

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

## Subsequent deploys

```
cd /mnt/data/sportscomm
git pull
bash deploy/deploy.sh
```

## Service controls

```
sudo systemctl status ui.service
sudo systemctl restart ui.service
sudo journalctl -u ui.service -f

sudo systemctl status caddy
sudo systemctl reload caddy
```

## Pipeline service

`pipeline.service` is installed but disabled by default. Enable once SRT
ingest is wired (Phase 1):

```
sudo systemctl enable pipeline.service
sudo systemctl start pipeline.service
```
