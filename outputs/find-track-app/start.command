#!/bin/zsh
cd "${0:A:h}"
if command -v python3 >/dev/null 2>&1; then
  python3 launch.py
  if [[ $? -ne 0 ]]; then
    read -r '?Press Enter to close.'
  fi
else
  echo 'Python 3 is required. Install Python 3, then run: python3 server.py'
  read -r '?Press Enter to close.'
fi
