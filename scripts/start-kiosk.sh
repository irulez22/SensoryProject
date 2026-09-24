#!/bin/bash
set -e
sleep 4
xset s off || true
xset -dpms || true
xset s noblank || true
unclutter -idle 0.5 -root &
exec chromium --kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble --disable-pinch --overscroll-history-navigation=0 http://127.0.0.1:8000/
