import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('launcher',Path(__file__).resolve().parents[1]/'launch.py')
launcher=importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)

class LauncherTests(TestCase):
    def test_reopening_reuses_server_and_opens_browser(self):
        with patch('sys.argv',['launch.py']),patch.object(launcher,'ready',return_value=True),patch.object(launcher.subprocess,'Popen') as spawn,patch.object(launcher.webbrowser,'open') as browser:
            self.assertEqual(launcher.main(),0)
            spawn.assert_not_called()
            browser.assert_called_once_with('http://127.0.0.1:8765')

    def test_no_browser_mode_does_not_open_a_tab(self):
        with patch('sys.argv',['launch.py','--no-browser']),patch.object(launcher,'ready',return_value=True),patch.object(launcher.webbrowser,'open') as browser:
            self.assertEqual(launcher.main(),0)
            browser.assert_not_called()
