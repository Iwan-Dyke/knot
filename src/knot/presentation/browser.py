"""Open a generated local artifact, including through a WSL host browser."""

import base64
import platform
import shutil
import subprocess
import webbrowser
from pathlib import Path


def open_view(path):
    path = Path(path).resolve()
    if 'microsoft' in platform.release().lower() and shutil.which('powershell.exe'):
        windows_path = subprocess.check_output(['wslpath', '-w', str(path)], text=True).strip()
        # Pass a quoted literal through an encoded command, preserving spaces and
        # apostrophes without interpolating a file path into shell syntax.
        command = "Start-Process -FilePath '" + windows_path.replace("'", "''") + "'"
        encoded = base64.b64encode(command.encode('utf-16le')).decode('ascii')
        subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
            check=True,
        )
    elif not webbrowser.open(path.as_uri()):
        raise RuntimeError(f'Could not open a browser; open {path} manually')
