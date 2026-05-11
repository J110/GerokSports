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

## GitHub Actions one-time setup (Workload Identity Federation)

Org policy blocks service-account JSON keys, so CI authenticates via WIF.

1. GCP Console → IAM → Service Accounts → create `qrackpot-github-actions`
2. Grant SA roles: `roles/compute.osAdminLogin`, `roles/iap.tunnelResourceAccessor`
3. Create a Workload Identity Pool (e.g. `github-actions-pool`) with an OIDC
   provider (`github`) trusting `https://token.actions.githubusercontent.com`,
   attribute condition restricting to this repo
   (`assertion.repository == 'J110/GerokSports'`)
4. Bind the GH identity to the SA:
   `roles/iam.workloadIdentityUser` on the SA for
   `principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions-pool/attribute.repository/J110/GerokSports`
5. GitHub repo → Settings → Secrets → Actions → add:
   - `WIF_PROVIDER` = `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions-pool/providers/github`
   - `GCP_SA_EMAIL` = `qrackpot-github-actions@qrackpot-prod.iam.gserviceaccount.com`

## Service controls (on VM, manual override only)

```
sudo systemctl status ui.service
sudo systemctl restart ui.service
sudo journalctl -u ui.service -f

sudo systemctl status caddy
sudo journalctl -u caddy -f
```

## Phase 1A — pipeline.service auto-deployed from CI

CI handles everything. One-time setup:

1. Add GitHub Actions secrets at https://github.com/J110/GerokSports/settings/secrets/actions
   - GROQ_API_KEY (required)
   - GEMINI_API_KEY (set to empty string if not used)

2. Push to derive-not-detect. CI will:
   - Run deploy.sh on the VM
   - Sync /etc/sportscomm/pipeline.env from GH secrets
   - Enable + restart pipeline.service
   - Health-check qrackpot.com
   - Dump last 30 lines of pipeline log into Action output

3. After CI goes green: open https://qrackpot.com
   - Pipeline replays the 30s test fixture
   - UI should show match state derived from the replay

## Pipeline service

`pipeline.service` is installed but disabled by default. Enable once SRT
ingest is wired (Phase 1):

```
sudo systemctl enable pipeline.service
sudo systemctl start pipeline.service
```

## Replay a recorded match (validates the server stack)

One-time setup:

1. Copy a representative mp4 to the VM. From your Mac:
```bash
   gcloud compute scp \
     --tunnel-through-iap \
     --zone=asia-south1-a \
     files/logs/deliveries/<sid>/match_<sid>.mp4 \
     qrackpot-prod-1:/mnt/data/recordings/match_replay.mp4
```
   (For faster validation, trim to ~5 min first with ffmpeg locally.)

2. Configure pipeline env via Cloud Console browser SSH on the VM:
```bash
   sudo cp deploy/pipeline.env.example /etc/sportscomm/pipeline.env
   sudo chmod 0600 /etc/sportscomm/pipeline.env
   sudo nano /etc/sportscomm/pipeline.env
   # Fill in GROQ_API_KEY, GEMINI_API_KEY at minimum
   # Set FRAME_FILE_PATH to the mp4 you uploaded
```

3. Trigger a redeploy from Cursor (any push to derive-not-detect re-runs the workflow)
   OR manually:
```bash
   sudo systemctl start pipeline.service
   sudo journalctl -u pipeline.service -f
```

4. Open https://qrackpot.com — should show the match state from the replay.

For a fast smoke without Groq cost: also upload `scout_raw.jsonl` from the
same session and set SCOUT_REPLAY_LOG to its path — pipeline replays
cached Scout calls instead of hitting Groq.
