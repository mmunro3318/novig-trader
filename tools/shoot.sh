#!/bin/bash
# usage: tools/shoot.sh name 'hash' [w h]
rm -f shots/proto-$1.png; google-chrome --user-data-dir=$(mktemp -d) --headless=new --no-sandbox --disable-gpu --hide-scrollbars --virtual-time-budget=${5:-25000} --window-size=${3:-1440},${4:-1000} --screenshot=$PWD/shots/proto-$1.png "http://localhost:8601/$2" 2>/dev/null
