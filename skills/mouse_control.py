import pyautogui


# Tetap aktif supaya mouse ke pojok kiri atas
# bisa menghentikan PyAutoGUI kalau ada perilaku aneh.
pyautogui.FAILSAFE = True


def _validate_position(x, y):
    width, height = pyautogui.size()

    if x is None or y is None:
        raise ValueError(
            "Koordinat x dan y diperlukan untuk aksi ini."
        )

    x = int(x)
    y = int(y)

    if not (
        0 <= x < width
        and
        0 <= y < height
    ):
        raise ValueError(
            f"Koordinat ({x}, {y}) berada di luar layar "
            f"{width}x{height}."
        )

    return x, y


def run(
    action: str,
    x=None,
    y=None,
    button: str = "left",
    amount: int = 0,
    duration: float = 0.3
):
    action = str(
        action or ""
    ).lower().strip()

    button = str(
        button or "left"
    ).lower().strip()

    try:
        duration = float(duration)
    except (TypeError, ValueError):
        duration = 0.3

    duration = max(
        0.0,
        min(duration, 5.0)
    )

    valid_buttons = {
        "left",
        "right",
        "middle"
    }

    if button not in valid_buttons:
        raise ValueError(
            f"Button '{button}' tidak valid."
        )

    # =====================================================
    # MOVE
    # =====================================================

    if action == "move":
        x, y = _validate_position(
            x,
            y
        )

        pyautogui.moveTo(
            x,
            y,
            duration=duration
        )

        return {
            "message": (
                f"Mouse berhasil dipindahkan "
                f"ke ({x}, {y})."
            ),
            "x": x,
            "y": y
        }

    # =====================================================
    # CLICK
    # =====================================================

    if action == "click":

        if x is not None or y is not None:
            x, y = _validate_position(
                x,
                y
            )

            pyautogui.click(
                x=x,
                y=y,
                button=button
            )

        else:
            pyautogui.click(
                button=button
            )

        return {
            "message": (
                f"Mouse berhasil melakukan "
                f"{button} click."
            )
        }

    # =====================================================
    # DOUBLE CLICK
    # =====================================================

    if action == "double_click":

        if x is not None or y is not None:
            x, y = _validate_position(
                x,
                y
            )

            pyautogui.doubleClick(
                x=x,
                y=y,
                button=button,
                interval=0.15
            )

        else:
            pyautogui.doubleClick(
                button=button,
                interval=0.15
            )

        return {
            "message": (
                f"Mouse berhasil melakukan "
                f"double click dengan tombol {button}."
            )
        }

    # =====================================================
    # RIGHT CLICK
    # =====================================================

    if action == "right_click":

        if x is not None or y is not None:
            x, y = _validate_position(
                x,
                y
            )

            pyautogui.rightClick(
                x=x,
                y=y
            )

        else:
            pyautogui.rightClick()

        return {
            "message": (
                "Mouse berhasil melakukan right click."
            )
        }

    # =====================================================
    # MIDDLE CLICK
    # =====================================================

    if action == "middle_click":

        if x is not None or y is not None:
            x, y = _validate_position(
                x,
                y
            )

            pyautogui.middleClick(
                x=x,
                y=y
            )

        else:
            pyautogui.middleClick()

        return {
            "message": (
                "Mouse berhasil melakukan middle click."
            )
        }

    # =====================================================
    # DRAG
    # =====================================================

    if action == "drag":
        x, y = _validate_position(
            x,
            y
        )

        pyautogui.dragTo(
            x,
            y,
            duration=duration,
            button=button
        )

        return {
            "message": (
                f"Mouse berhasil drag ke ({x}, {y}) "
                f"dengan tombol {button}."
            ),
            "x": x,
            "y": y
        }

    # =====================================================
    # SCROLL
    # =====================================================

    if action == "scroll":

        try:
            amount = int(amount)

        except (TypeError, ValueError):
            raise ValueError(
                "amount scroll harus berupa angka."
            )

        if amount == 0:
            raise ValueError(
                "amount scroll tidak boleh 0."
            )

        pyautogui.scroll(
            amount
        )

        return {
            "message": (
                f"Mouse berhasil scroll sebesar {amount}."
            ),
            "amount": amount
        }

    # =====================================================
    # MOVE RELATIVE
    # =====================================================

    if action == "move_relative":

        if x is None or y is None:
            raise ValueError(
                "x dan y diperlukan sebagai offset relatif."
            )

        dx = int(x)
        dy = int(y)

        current_x, current_y = (
            pyautogui.position()
        )

        target_x = current_x + dx
        target_y = current_y + dy

        target_x, target_y = (
            _validate_position(
                target_x,
                target_y
            )
        )

        pyautogui.moveTo(
            target_x,
            target_y,
            duration=duration
        )

        return {
            "message": (
                f"Mouse berhasil digeser relatif "
                f"ke ({target_x}, {target_y})."
            ),
            "x": target_x,
            "y": target_y
        }

    raise ValueError(
        f"Action '{action}' tidak dikenal."
    )


TOOL = {
    "name": "mouse_control",

    "description": (
        "Mengontrol mouse Windows secara lengkap. "
        "Dapat memindahkan cursor, click, double click, "
        "right click, middle click, drag, scroll, dan "
        "bergerak relatif dari posisi saat ini. "
        "Gunakan screen_state terlebih dahulu jika koordinat "
        "target harus ditentukan berdasarkan keadaan layar."
    ),

    "parameters": {
        "action": {
            "type": "string",
            "description": (
                "Aksi mouse: move, click, double_click, "
                "right_click, middle_click, drag, scroll, "
                "atau move_relative."
            )
        },

        "x": {
            "type": "integer",
            "description": (
                "Koordinat X untuk move/click/drag. "
                "Untuk move_relative berarti offset horizontal."
            )
        },

        "y": {
            "type": "integer",
            "description": (
                "Koordinat Y untuk move/click/drag. "
                "Untuk move_relative berarti offset vertikal."
            )
        },

        "button": {
            "type": "string",
            "description": (
                "Tombol mouse: left, right, atau middle. "
                "Default left."
            )
        },

        "amount": {
            "type": "integer",
            "description": (
                "Jumlah scroll. Positif scroll ke atas, "
                "negatif scroll ke bawah."
            )
        },

        "duration": {
            "type": "number",
            "description": (
                "Durasi gerakan mouse dalam detik. "
                "Default 0.3."
            )
        }
    },

    "run": run
}