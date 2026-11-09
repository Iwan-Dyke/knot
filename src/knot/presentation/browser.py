"""Open a generated local artifact, including through a WSL host browser."""

import base64
import platform
import shutil
import subprocess
import webbrowser
from pathlib import Path


def open_url(url: str) -> None:
    """Open an explicit URL, including in the WSL host browser."""
    if 'microsoft' in platform.release().lower() and shutil.which('powershell.exe'):
        # Pass a quoted literal through an encoded command, preserving spaces and
        # apostrophes without interpolating a file path into shell syntax.
        command = "Start-Process -FilePath '" + url.replace("'", "''") + "'"
        encoded = base64.b64encode(command.encode('utf-16le')).decode('ascii')
        subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
            check=True,
        )
    elif not webbrowser.open(url):
        raise RuntimeError('Could not open a browser; use the printed location manually')


def open_view(path):
    path = Path(path).resolve()
    if 'microsoft' in platform.release().lower() and shutil.which('powershell.exe'):
        target = subprocess.check_output(['wslpath', '-w', str(path)], text=True).strip()
    else:
        target = path.as_uri()
    open_url(target)
