import time
import pyautogui


def run(text: str, interval: float = 0.03):
    if not text:
        raise ValueError("Teks kosong")

    time.sleep(0.5)

    pyautogui.write(
        text,
        interval=interval
    )

    return {
        "message": f"Mengetik teks: {text}"
    }


TOOL = {
    "name": "type_text",
    "description": "Mengetik teks ke aplikasi atau jendela Windows yang sedang aktif.",
    "parameters": {
        "text": {
            "type": "string",
            "description": "Teks yang ingin diketik"
        },
        "interval": {
            "type": "number",
            "description": "Jeda antar karakter dalam detik, default 0.03"
        }
    },
    "run": run
}