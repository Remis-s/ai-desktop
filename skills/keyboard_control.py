import time
import pyautogui


pyautogui.FAILSAFE = True


def _clean_key(key):
    key = str(
        key or ""
    ).strip().lower()

    if not key:
        raise ValueError(
            "Nama tombol kosong."
        )

    return key


def run(
    action: str,
    key: str = "",
    keys=None,
    text: str = "",
    presses: int = 1,
    interval: float = 0.03,
    hold_seconds: float = 0.5
):
    action = str(
        action or ""
    ).lower().strip()

    try:
        interval = float(interval)

    except (TypeError, ValueError):
        interval = 0.03

    interval = max(
        0.0,
        min(interval, 2.0)
    )

    try:
        presses = int(presses)

    except (TypeError, ValueError):
        presses = 1

    presses = max(
        1,
        min(presses, 100)
    )

    try:
        hold_seconds = float(
            hold_seconds
        )

    except (TypeError, ValueError):
        hold_seconds = 0.5

    hold_seconds = max(
        0.0,
        min(hold_seconds, 10.0)
    )

    # =====================================================
    # PRESS
    # =====================================================

    if action == "press":

        key = _clean_key(
            key
        )

        pyautogui.press(
            key,
            presses=presses,
            interval=interval
        )

        return {
            "message": (
                f"Tombol '{key}' berhasil ditekan "
                f"{presses} kali."
            ),
            "key": key,
            "presses": presses
        }

    # =====================================================
    # HOTKEY
    # =====================================================

    if action == "hotkey":

        if keys is None:
            raise ValueError(
                "Daftar tombol hotkey kosong."
            )

        if isinstance(
            keys,
            str
        ):

            # Bisa menerima:
            # "ctrl+shift+s"
            keys = [
                item.strip()
                for item in keys.split("+")
                if item.strip()
            ]

        if not isinstance(
            keys,
            list
        ):

            raise ValueError(
                "keys harus berupa list tombol."
            )

        cleaned_keys = [
            _clean_key(item)
            for item in keys
        ]

        if len(cleaned_keys) < 2:

            raise ValueError(
                "Hotkey membutuhkan minimal 2 tombol."
            )

        pyautogui.hotkey(
            *cleaned_keys
        )

        return {
            "message": (
                "Hotkey berhasil ditekan: "
                + " + ".join(cleaned_keys)
            ),
            "keys": cleaned_keys
        }

    # =====================================================
    # WRITE
    # =====================================================

    if action == "write":

        text = str(
            text or ""
        )

        if not text:
            raise ValueError(
                "Teks yang ingin diketik kosong."
            )

        pyautogui.write(
            text,
            interval=interval
        )

        return {
            "message": (
                "Teks berhasil diketik."
            ),
            "text": text
        }

    # =====================================================
    # KEY DOWN
    # =====================================================

    if action == "key_down":

        key = _clean_key(
            key
        )

        pyautogui.keyDown(
            key
        )

        return {
            "message": (
                f"Tombol '{key}' sedang ditahan."
            ),
            "key": key
        }

    # =====================================================
    # KEY UP
    # =====================================================

    if action == "key_up":

        key = _clean_key(
            key
        )

        pyautogui.keyUp(
            key
        )

        return {
            "message": (
                f"Tombol '{key}' dilepas."
            ),
            "key": key
        }

    # =====================================================
    # HOLD
    # =====================================================

    if action == "hold":

        key = _clean_key(
            key
        )

        pyautogui.keyDown(
            key
        )

        try:

            time.sleep(
                hold_seconds
            )

        finally:

            # Selalu dilepas walaupun terjadi error.
            pyautogui.keyUp(
                key
            )

        return {
            "message": (
                f"Tombol '{key}' berhasil ditahan "
                f"selama {hold_seconds} detik."
            ),
            "key": key,
            "hold_seconds": hold_seconds
        }

    raise ValueError(
        f"Action keyboard '{action}' tidak dikenal."
    )


TOOL = {
    "name": "keyboard_control",

    "description": (
        "Mengontrol keyboard Windows. "
        "Dapat menekan tombol, menekan tombol beberapa kali, "
        "menjalankan hotkey/shortcut, mengetik teks, "
        "menahan tombol, serta melakukan key_down dan key_up. "
        "Gunakan focus_window terlebih dahulu jika tindakan "
        "harus dilakukan pada aplikasi tertentu."
    ),

    "parameters": {
        "action": {
            "type": "string",
            "description": (
                "Aksi keyboard: press, hotkey, write, "
                "key_down, key_up, atau hold."
            )
        },

        "key": {
            "type": "string",
            "description": (
                "Nama tombol untuk press, hold, key_down, atau key_up. "
                "Contoh: enter, esc, tab, space, left, right, f5."
            )
        },

        "keys": {
            "type": "array",
            "description": (
                "Daftar tombol untuk hotkey. "
                "Contoh: ['ctrl', 'shift', 's']."
            )
        },

        "text": {
            "type": "string",
            "description": (
                "Teks yang akan diketik jika action=write."
            )
        },

        "presses": {
            "type": "integer",
            "description": (
                "Jumlah penekanan tombol untuk action=press. "
                "Default 1."
            )
        },

        "interval": {
            "type": "number",
            "description": (
                "Jeda antar penekanan/karakter dalam detik."
            )
        },

        "hold_seconds": {
            "type": "number",
            "description": (
                "Durasi menahan tombol jika action=hold."
            )
        }
    },

    "run": run
}