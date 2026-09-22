import os
import re
import shutil
import subprocess
from pathlib import Path

try:
    import winreg
except ImportError:
    winreg = None


def normalize(text):
    return re.sub(
        r"[^a-z0-9]",
        "",
        text.lower()
    )


def start_target(target):
    try:
        os.startfile(target)
        return True
    except Exception:
        return False


def find_command(app_name):
    command = shutil.which(app_name)

    if command:
        return command

    return None


def shortcut_locations():
    locations = []

    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("PROGRAMDATA")
    userprofile = os.environ.get("USERPROFILE")

    if appdata:
        locations.append(
            Path(appdata) /
            "Microsoft" /
            "Windows" /
            "Start Menu" /
            "Programs"
        )

    if programdata:
        locations.append(
            Path(programdata) /
            "Microsoft" /
            "Windows" /
            "Start Menu" /
            "Programs"
        )

    if userprofile:
        locations.append(
            Path(userprofile) /
            "Desktop"
        )

    public = os.environ.get("PUBLIC")

    if public:
        locations.append(
            Path(public) /
            "Desktop"
        )

    return locations


def find_shortcut(app_name):
    wanted = normalize(app_name)

    candidates = []

    for root in shortcut_locations():

        if not root.exists():
            continue

        try:
            for path in root.rglob("*"):

                if path.suffix.lower() not in (
                    ".lnk",
                    ".url"
                ):
                    continue

                name = normalize(path.stem)

                if name == wanted:
                    return str(path)

                if wanted in name or name in wanted:
                    candidates.append(path)

        except Exception:
            continue

    if candidates:
        candidates.sort(
            key=lambda x: len(x.stem)
        )

        return str(
            candidates[0]
        )

    return None


def registry_locations():
    return [
        (
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
        )
    ]


def read_reg_value(key, name):
    try:
        value, _ = winreg.QueryValueEx(
            key,
            name
        )

        return value

    except OSError:
        return None


def clean_icon_path(value):
    if not value:
        return None

    value = value.strip().strip('"')

    # DisplayIcon kadang:
    # "C:\Program Files\App\App.exe",0

    if "," in value:
        value = value.rsplit(
            ",",
            1
        )[0]

    return value.strip().strip('"')


def find_from_registry(app_name):
    if winreg is None:
        return None

    wanted = normalize(app_name)

    matches = []

    for hive, location in registry_locations():

        try:
            root = winreg.OpenKey(
                hive,
                location
            )

        except OSError:
            continue

        try:
            count = winreg.QueryInfoKey(
                root
            )[0]

            for i in range(count):

                try:
                    sub_name = winreg.EnumKey(
                        root,
                        i
                    )

                    sub = winreg.OpenKey(
                        root,
                        sub_name
                    )

                    display_name = read_reg_value(
                        sub,
                        "DisplayName"
                    )

                    if not display_name:
                        sub.Close()
                        continue

                    normalized_display = normalize(
                        display_name
                    )

                    if (
                        wanted not in normalized_display
                        and
                        normalized_display not in wanted
                    ):
                        sub.Close()
                        continue

                    icon = clean_icon_path(
                        read_reg_value(
                            sub,
                            "DisplayIcon"
                        )
                    )

                    install_location = read_reg_value(
                        sub,
                        "InstallLocation"
                    )

                    matches.append(
                        {
                            "name": display_name,
                            "icon": icon,
                            "location": install_location
                        }
                    )

                    sub.Close()

                except OSError:
                    continue

        finally:
            root.Close()

    for match in matches:

        icon = match["icon"]

        if (
            icon
            and
            os.path.isfile(icon)
            and
            icon.lower().endswith(".exe")
        ):
            return icon

    return None


def run(app_name: str):
    app_name = app_name.strip()

    if not app_name:
        raise ValueError(
            "Nama aplikasi kosong"
        )

    # 1. User memberikan path langsung.
    if os.path.exists(app_name):

        if start_target(app_name):

            return {
                "message": f"Membuka {app_name}",
                "method": "path"
            }

    # 2. Command Windows / executable di PATH.
    command = find_command(
        app_name
    )

    if command:

        try:
            subprocess.Popen(
                [command]
            )

            return {
                "message": f"Membuka {app_name}",
                "method": "command",
                "target": command
            }

        except Exception as e:
            raise RuntimeError(
                f"Gagal membuka {app_name}: {e}"
            )

    # 3. Shortcut Start Menu / Desktop.
    shortcut = find_shortcut(
        app_name
    )

    if shortcut:

        if start_target(shortcut):

            return {
                "message": f"Membuka {app_name}",
                "method": "shortcut",
                "target": shortcut
            }

    # 4. Installed application dari Registry.
    executable = find_from_registry(
        app_name
    )

    if executable:

        if start_target(executable):

            return {
                "message": f"Membuka {app_name}",
                "method": "registry",
                "target": executable
            }

    # Jangan pura-pura berhasil.
    raise RuntimeError(
        f"Aplikasi '{app_name}' tidak ditemukan di Windows."
    )


TOOL = {
    "name": "open_app",

    "description": (
        "Membuka aplikasi Windows berdasarkan nama aplikasi. "
        "Dapat mencari command, shortcut Start Menu/Desktop, "
        "atau aplikasi terpasang di Windows."
    ),

    "parameters": {
        "app_name": {
            "type": "string",
            "description": (
                "Nama aplikasi yang ingin dibuka, "
                "contoh: Notepad, Spotify, Genshin Impact, Discord"
            )
        }
    },

    "run": run
}