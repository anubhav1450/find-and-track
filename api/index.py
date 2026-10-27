"""Vercel Python Function; the private local server remains separate."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs'/'find-track-app'))
from cloud import make_handler
class handler(make_handler()):
    pass
