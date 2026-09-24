SENSORY WORLD v0.6

Upload the CONTENTS of this folder to ~/bubbleworld using FileZilla.

Then SSH into the Pi and run:

cd ~/bubbleworld
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python server.py

Test:
  Screen: http://bubbleworld.local:8000/
  Phone admin: http://bubbleworld.local:8000/admin

IMPORTANT: stop the old `python3 -m http.server 8000` first if it is still running.

Once tested, install the automatic server service:

sed "s/REPLACE_USER/$USER/g" systemd/sensory-world.service | sudo tee /etc/systemd/system/sensory-world.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now sensory-world.service
sudo systemctl status sensory-world.service

KIOSK PACKAGES (Raspberry Pi OS Lite / Debian package names can vary by release):
  sudo apt update
  sudo apt install --no-install-recommends xserver-xorg x11-xserver-utils xinit openbox chromium unclutter -y

Before enabling automatic kiosk startup, test it manually from a local display session.
The included scripts/start-kiosk.sh launches Chromium at http://127.0.0.1:8000/.

Reboot button:
For the admin Reboot Pi button to work without a password prompt, add a narrow sudoers rule using `sudo visudo`:
  REPLACE_USER ALL=(root) NOPASSWD: /sbin/reboot
Replace REPLACE_USER with your actual Pi username.

SECURITY:
This v0.6 admin panel is intended for a trusted local Wi-Fi network. It has no login yet. Do not port-forward port 8000 to the public internet.


v0.6: Admin panel now includes four large virtual sensory buttons. Button DOWN/UP events travel through the same WebSocket path intended for future GPIO controls.
