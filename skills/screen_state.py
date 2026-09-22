import pyautogui
import pygetwindow as gw


def run(
    include_windows: bool = True,
    max_windows: int = 20
):
    # ==========================================
    # SCREEN
    # ==========================================

    screen_width, screen_height = pyautogui.size()

    # ==========================================
    # MOUSE
    # ==========================================

    mouse_x, mouse_y = pyautogui.position()

    # ==========================================
    # ACTIVE WINDOW
    # ==========================================

    active_window = None

    try:
        active = gw.getActiveWindow()

        if active:
            active_window = {
                "title": active.title,
                "x": active.left,
                "y": active.top,
                "width": active.width,
                "height": active.height,
                "minimized": active.isMinimized,
                "maximized": active.isMaximized
            }

    except Exception:
        active_window = None

    # ==========================================
    # WINDOWS
    # ==========================================

    windows = []

    if include_windows:

        try:
            all_windows = gw.getAllWindows()

            for window in all_windows:

                if len(windows) >= max_windows:
                    break

                try:
                    title = str(
                        window.title or ""
                    ).strip()

                    # Abaikan window tanpa judul.
                    if not title:
                        continue

                    # Abaikan window ukuran nol.
                    if (
                        window.width <= 0
                        or
                        window.height <= 0
                    ):
                        continue

                    windows.append({
                        "title": title,
                        "x": window.left,
                        "y": window.top,
                        "width": window.width,
                        "height": window.height,
                        "minimized": window.isMinimized,
                        "maximized": window.isMaximized
                    })

                except Exception:
                    continue

        except Exception as error:
            raise RuntimeError(
                f"Gagal membaca daftar window: {error}"
            )

    # ==========================================
    # RESULT
    # ==========================================

    return {
        "message": "Keadaan desktop berhasil dibaca.",

        "screen": {
            "width": screen_width,
            "height": screen_height
        },

        "mouse": {
            "x": mouse_x,
            "y": mouse_y
        },

        "active_window": active_window,

        "windows": windows
    }


TOOL = {
    "name": "screen_state",

    "description": (
        "Membaca keadaan desktop Windows saat ini, termasuk "
        "ukuran layar, posisi mouse, window aktif, serta posisi "
        "dan ukuran window aplikasi yang terbuka. Gunakan tool ini "
        "ketika Pochi perlu mengetahui apa yang sedang terjadi "
        "di desktop sebelum melakukan gerakan atau tindakan."
    ),

    "parameters": {
        "include_windows": {
            "type": "boolean",
            "description": (
                "Jika true, sertakan daftar window yang terbuka. "
                "Default true."
            )
        },

        "max_windows": {
            "type": "integer",
            "description": (
                "Jumlah maksimum window yang dikembalikan. "
                "Default 20."
            )
        }
    },

    "run": run
}