# Google Cloud VM Deployment

This project can run continuously on an Ubuntu VM with `systemd`, so alerts keep arriving even when your PC is off.

## 1. Create a VM

- Google Cloud Console
- Compute Engine
- Create VM
- Recommended: Ubuntu 24.04 LTS, e2-micro or higher
- Allow HTTP/HTTPS is optional for this bot

## 2. Connect to the VM

```bash
gcloud compute ssh <YOUR_VM_NAME> --zone <YOUR_ZONE>
```

Or use the SSH button in the Google Cloud Console.

## 3. Install packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

## 4. Clone the repo

```bash
cd /home/ubuntu
git clone https://github.com/davidkim3028-rgb/circle-monitor.git
cd circle-monitor
```

## 5. Create the Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e '.[dev]'
```

## 6. Prepare config

```bash
cp config.example.toml config.toml
mkdir -p data logs
```

Edit `config.toml`:

- Set `request_contact_email`
- Keep `enabled = ["telegram"]` if you only want Telegram alerts
- Leave Telegram token and chat ID blank in the file because they will come from the env file

## 7. Create the env file

```bash
cp deploy/gcp/circle-monitor.env.example deploy/gcp/circle-monitor.env
nano deploy/gcp/circle-monitor.env
```

Example:

```env
TELEGRAM_BOT_TOKEN=123456:ABCDEF
TELEGRAM_CHAT_ID=123456789
# OPENAI_API_KEY=sk-...
```

## 8. Test once before enabling the service

```bash
set -a
source deploy/gcp/circle-monitor.env
set +a

.venv/bin/python -m circle_monitor.cli --config config.toml --once
```

If Telegram receives a message, move on.

## 9. Install the systemd service

```bash
sudo cp deploy/gcp/circle-monitor.service /etc/systemd/system/circle-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable circle-monitor
sudo systemctl start circle-monitor
```

## 10. Check status and logs

```bash
sudo systemctl status circle-monitor
journalctl -u circle-monitor -f
```

## 11. Update later

```bash
cd /home/ubuntu/circle-monitor
git pull
source .venv/bin/activate
pip install -e '.[dev]'
sudo systemctl restart circle-monitor
```

## Notes

- The bot now re-alerts duplicate items if they have not been sent in the last 12 hours.
- If you only want Telegram and not local stdout alerts, set:

```toml
[notifications]
enabled = ["telegram"]
```
