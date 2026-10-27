#!/usr/bin/env python3
"""Start the local app once, reuse it on later launches, and open the browser."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen
from urllib.error import URLError
import webbrowser

ROOT = Path(__file__).resolve().parent

def ready(url):
    try:
        with urlopen(url + '/api/state', timeout=0.8) as response:
            result = json.load(response)
            return response.status == 200 and result.get('data', {}).get('schema') == 1
    except (URLError, OSError, ValueError):
        return False

def main():
    parser = argparse.ArgumentParser(description='Open Find&Track')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    url = 'http://127.0.0.1:' + str(args.port)
    if not ready(url):
        directory = ROOT / 'data'
        directory.mkdir(exist_ok=True)
        logfile = directory / 'server.log'
        with logfile.open('ab') as output:
            interpreter = ROOT.parents[1] / '.venv' / 'bin' / 'python3'
            process = subprocess.Popen([str(interpreter) if interpreter.exists() else sys.executable, str(ROOT / 'server.py'), '--port', str(args.port)], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
        logfile.chmod(0o600)
        for _ in range(60):
            if ready(url):
                break
            if process.poll() is not None:
                print('Find&Track could not start. See data/server.log for details.', file=sys.stderr)
                return 1
            time.sleep(0.15)
        else:
            print('Find&Track is taking longer to start. Open ' + url + ' in a moment.', file=sys.stderr)
            return 1
    if not args.no_browser:
        webbrowser.open(url)
    print('Find&Track: ' + url)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
