import os
from datetime import datetime

from mss import mss
from mss.tools import to_png


BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

SCREENSHOT_DIR = os.path.join(
    BASE_DIR,
    "runtime",
    "screenshots"
)

os.makedirs(
    SCREENSHOT_DIR,
    exist_ok=True
)


def run(
    mode: str = "latest",
    x=None,
    y=None,
    width=None,
    height=None
):
    mode = str(
        mode or "latest"
    ).lower().strip()

    # =====================================================
    # FILE NAME
    # =====================================================

    if mode == "timestamp":

        stamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        filename = (
            f"screen_{stamp}.png"
        )

    else:

        filename = "latest.png"

    output_path = os.path.join(
        SCREENSHOT_DIR,
        filename
    )

    # =====================================================
    # CAPTURE
    # =====================================================

    try:

        with mss() as sct:

            # =============================================
            # FULL PRIMARY MONITOR
            # =============================================

            if (
                x is None
                and
                y is None
                and
                width is None
                and
                height is None
            ):

                # monitors[0] = seluruh virtual desktop
                # monitors[1] = primary monitor
                monitor = sct.monitors[1]

                shot = sct.grab(
                    monitor
                )

                to_png(
                    shot.rgb,
                    shot.size,
                    output=output_path
                )

                return {
                    "message": (
                        "Screenshot desktop berhasil diambil."
                    ),

                    "path": output_path,

                    "width": shot.width,

                    "height": shot.height,

                    "region": None
                }

            # =============================================
            # REGION VALIDATION
            # =============================================

            if (
                x is None
                or
                y is None
                or
                width is None
                or
                height is None
            ):

                raise ValueError(
                    "Untuk screenshot region, "
                    "x, y, width, dan height wajib diisi."
                )

            try:

                x = int(x)
                y = int(y)
                width = int(width)
                height = int(height)

            except (
                TypeError,
                ValueError
            ):

                raise ValueError(
                    "Koordinat screenshot harus berupa angka."
                )

            if width <= 0 or height <= 0:

                raise ValueError(
                    "Width dan height harus lebih besar dari 0."
                )

            # =============================================
            # SCREEN BOUNDS
            # =============================================

            primary = sct.monitors[1]

            screen_left = primary["left"]
            screen_top = primary["top"]

            screen_right = (
                screen_left
                + primary["width"]
            )

            screen_bottom = (
                screen_top
                + primary["height"]
            )

            if (
                x < screen_left
                or
                y < screen_top
                or
                x + width > screen_right
                or
                y + height > screen_bottom
            ):

                raise ValueError(
                    "Region screenshot berada di luar layar utama."
                )

            region = {
                "left": x,
                "top": y,
                "width": width,
                "height": height
            }

            shot = sct.grab(
                region
            )

            to_png(
                shot.rgb,
                shot.size,
                output=output_path
            )

            return {
                "message": (
                    "Screenshot region berhasil diambil."
                ),

                "path": output_path,

                "width": shot.width,

                "height": shot.height,

                "region": {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height
                }
            }

    except Exception as error:

        raise RuntimeError(
            f"Gagal mengambil screenshot: {error}"
        )


TOOL = {
    "name": "screen_capture",

    "description": (
        "Mengambil screenshot desktop Windows atau region tertentu "
        "dan menyimpannya sebagai PNG. "
        "Gunakan tool ini saat Pochi membutuhkan informasi visual layar."
    ),

    "parameters": {
        "mode": {
            "type": "string",
            "description": (
                "latest untuk menimpa screenshot terakhir "
                "atau timestamp untuk membuat file baru."
            )
        },

        "x": {
            "type": "integer",
            "description": (
                "Posisi X awal untuk screenshot region."
            )
        },

        "y": {
            "type": "integer",
            "description": (
                "Posisi Y awal untuk screenshot region."
            )
        },

        "width": {
            "type": "integer",
            "description": (
                "Lebar screenshot region."
            )
        },

        "height": {
            "type": "integer",
            "description": (
                "Tinggi screenshot region."
            )
        }
    },

    "run": run
}