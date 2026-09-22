import pygetwindow as gw


def run(title: str):
    title = title.strip()

    if not title:
        raise ValueError("Judul window kosong")

    windows = gw.getWindowsWithTitle(title)

    if not windows:
        raise RuntimeError(f"Window dengan judul '{title}' tidak ditemukan")

    win = windows[0]

    if win.isMinimized:
        win.restore()

    win.activate()

    return {
        "message": f"Fokus ke window: {win.title}"
    }


TOOL = {
    "name": "focus_window",
    "description": "Memfokuskan jendela aplikasi Windows berdasarkan judul window.",
    "parameters": {
        "title": {
            "type": "string",
            "description": "Judul window, contoh: Notepad"
        }
    },
    "run": run
}