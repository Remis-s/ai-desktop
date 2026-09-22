import ast
import json
import os
import re

import ollama

from PIL import Image


# =========================================================
# CONFIG
# =========================================================

VISION_MODEL = "qwen2.5vl:3b"

# Context 4096 terlalu kecil untuk screenshot 2560x1440.
VISION_CONTEXT = 8192

# Toleransi kecil jika model memberikan koordinat tepat
# di batas gambar.
#
# Contoh:
#
# width = 1800
# model x = 1800
#
# Pixel valid sebenarnya 0..1799.
VISION_COORDINATE_TOLERANCE = 2


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

SCREENSHOT_DIR = os.path.join(
    BASE_DIR,
    "runtime",
    "screenshots"
)


# =========================================================
# JSON MODE DETECTION
# =========================================================

def _instruction_requests_json(
    instruction
):
    """
    Caller lama tidak perlu diubah.

    Jika prompt vision memang meminta output JSON,
    vision_runtime otomatis memakai JSON mode Ollama.

    Prompt natural seperti screen_vision tetap menghasilkan
    teks biasa.
    """

    text = str(
        instruction or ""
    ).lower()

    json_markers = (
        "balas hanya json",
        "jawab hanya json",
        "output hanya json",
        "return only json",
        "respond only json",
        "jangan gunakan markdown",
        "\"found\"",
        "\"can_navigate\"",
        "\"verified\""
    )

    return any(
        marker in text
        for marker in json_markers
    )


# =========================================================
# REMOVE MARKDOWN CODE FENCE
# =========================================================

def _strip_code_fence(
    text
):

    text = str(
        text or ""
    ).strip()

    if not text.startswith(
        "```"
    ):
        return text

    lines = text.splitlines()

    if lines:
        lines = lines[1:]

    if (
        lines
        and
        lines[-1].strip().startswith(
            "```"
        )
    ):
        lines = lines[:-1]

    return "\n".join(
        lines
    ).strip()


# =========================================================
# EXTRACT POSSIBLE JSON OBJECT
# =========================================================

def _extract_object_text(
    text
):

    text = _strip_code_fence(
        text
    )

    start = text.find(
        "{"
    )

    end = text.rfind(
        "}"
    )

    if (
        start == -1
        or
        end == -1
        or
        end <= start
    ):
        return None

    return text[
        start:end + 1
    ].strip()


# =========================================================
# RELAXED JSON PARSER
# =========================================================

def _loads_relaxed_object(
    text
):
    """
    Mencoba beberapa bentuk output model:

    JSON valid:
        {"found": true}

    Python-like:
        {'found': True}

    Bare keys:
        {found: true, x: 10}

    Trailing comma:
        {"found": true,}

    Hasil akhirnya selalu Python dict
    atau None jika memang tidak bisa diselamatkan.
    """

    candidate = _extract_object_text(
        text
    )

    if not candidate:
        return None

    # =====================================================
    # 1. NORMAL JSON
    # =====================================================

    try:

        data = json.loads(
            candidate
        )

        if isinstance(
            data,
            dict
        ):
            return data

    except (
        json.JSONDecodeError,
        TypeError,
        ValueError
    ):
        pass

    # =====================================================
    # 2. PYTHON-LIKE DICT
    # =====================================================

    try:

        data = ast.literal_eval(
            candidate
        )

        if isinstance(
            data,
            dict
        ):
            return data

    except (
        SyntaxError,
        ValueError
    ):
        pass

    # =====================================================
    # 3. REPAIR COMMON MODEL JSON ERRORS
    # =====================================================

    repaired = candidate

    # Quote bare keys:
    #
    # {found: true}
    #
    # ->
    #
    # {"found": true}
    repaired = re.sub(
        r'([\{\[,]\s*)'
        r'([A-Za-z_][A-Za-z0-9_\-]*)'
        r'\s*:',
        r'\1"\2":',
        repaired
    )

    # Remove trailing comma.
    repaired = re.sub(
        r",\s*([}\]])",
        r"\1",
        repaired
    )

    try:

        data = json.loads(
            repaired
        )

        if isinstance(
            data,
            dict
        ):
            return data

    except (
        json.JSONDecodeError,
        TypeError,
        ValueError
    ):
        pass

    # =====================================================
    # 4. REPAIR AS PYTHON DICT
    # =====================================================

    python_like = re.sub(
        r"\btrue\b",
        "True",
        repaired,
        flags=re.IGNORECASE
    )

    python_like = re.sub(
        r"\bfalse\b",
        "False",
        python_like,
        flags=re.IGNORECASE
    )

    python_like = re.sub(
        r"\bnull\b",
        "None",
        python_like,
        flags=re.IGNORECASE
    )

    try:

        data = ast.literal_eval(
            python_like
        )

        if isinstance(
            data,
            dict
        ):
            return data

    except (
        SyntaxError,
        ValueError
    ):
        pass

    return None


# =========================================================
# NORMALIZE BOOLEAN FIELDS
# =========================================================

def _normalize_boolean_fields(
    data
):

    for key in (
        "found",
        "can_navigate",
        "verified"
    ):

        if key not in data:
            continue

        value = data.get(
            key
        )

        if isinstance(
            value,
            str
        ):

            value_lower = (
                value.strip().lower()
            )

            if value_lower == "true":
                data[key] = True

            elif value_lower == "false":
                data[key] = False

            elif value_lower in (
                "null",
                "none",
                ""
            ):
                data[key] = None

    return data


# =========================================================
# NORMALIZE CONFIDENCE
# =========================================================

def _normalize_confidence(
    data
):

    if "confidence" not in data:
        return data

    try:

        confidence = float(
            data.get(
                "confidence"
            )
        )

    except (
        TypeError,
        ValueError
    ):

        data[
            "confidence"
        ] = 0.0

        return data

    data[
        "confidence"
    ] = max(
        0.0,
        min(
            confidence,
            1.0
        )
    )

    return data


# =========================================================
# MARK VISUAL RESULT NOT FOUND
# =========================================================

def _mark_not_found(
    data,
    reason
):

    data[
        "found"
    ] = False

    data[
        "x"
    ] = None

    data[
        "y"
    ] = None

    data[
        "confidence"
    ] = 0.0

    old_description = str(
        data.get(
            "description",
            ""
        )
        or ""
    ).strip()

    if old_description:

        data[
            "description"
        ] = (
            old_description
            +
            " | "
            +
            reason
        )

    else:

        data[
            "description"
        ] = reason

    return data


# =========================================================
# COORDINATE SANITIZER
# =========================================================

def _sanitize_vision_coordinates(
    data,
    image_path
):
    """
    Mencegah error seperti:

    image = 1800 x 983
    model = x=1800, y=983

    Karena koordinat valid:
    x = 0..1799
    y = 0..982

    Kesalahan tepat di boundary dianggap kesalahan kecil
    model dan di-clamp.

    Koordinat yang jauh di luar gambar dianggap
    hasil vision tidak valid -> found=False.
    """

    if data.get(
        "found"
    ) is not True:

        # Jika model bilang tidak ditemukan,
        # kosongkan koordinat agar konsisten.
        if "found" in data:

            data[
                "x"
            ] = None

            data[
                "y"
            ] = None

        return data

    # Hanya sanitizer localization.
    # JSON planner/verifier mungkin tidak punya x/y.
    if (
        "x" not in data
        or
        "y" not in data
    ):
        return data

    raw_x = data.get(
        "x"
    )

    raw_y = data.get(
        "y"
    )

    if (
        isinstance(
            raw_x,
            bool
        )
        or
        isinstance(
            raw_y,
            bool
        )
    ):

        return _mark_not_found(
            data,
            "Koordinat vision bertipe boolean dan tidak valid."
        )

    try:

        x = int(
            round(
                float(
                    raw_x
                )
            )
        )

        y = int(
            round(
                float(
                    raw_y
                )
            )
        )

    except (
        TypeError,
        ValueError
    ):

        return _mark_not_found(
            data,
            "Koordinat vision tidak dapat dibaca sebagai angka."
        )

    try:

        with Image.open(
            image_path
        ) as image:

            width, height = (
                image.size
            )

    except Exception:

        # Kalau ukuran gambar tidak bisa dibaca,
        # jangan merusak result yang sebenarnya valid.
        data[
            "x"
        ] = x

        data[
            "y"
        ] = y

        return data

    if (
        width <= 0
        or
        height <= 0
    ):

        return _mark_not_found(
            data,
            "Ukuran gambar vision tidak valid."
        )

    # =====================================================
    # CHECK X
    # =====================================================

    x_valid = (
        0 <= x < width
    )

    if not x_valid:

        # Toleransi hanya untuk kesalahan sangat kecil
        # tepat di tepi gambar.
        if (
            -VISION_COORDINATE_TOLERANCE
            <= x
            <= (
                width
                - 1
                +
                VISION_COORDINATE_TOLERANCE
            )
        ):

            old_x = x

            x = max(
                0,
                min(
                    x,
                    width - 1
                )
            )

            print(
                "[VISION] "
                f"Koordinat X boundary dikoreksi: "
                f"{old_x} -> {x}"
            )

        else:

            return _mark_not_found(
                data,
                (
                    f"Koordinat X vision {x} "
                    f"jauh di luar gambar "
                    f"lebar {width}."
                )
            )

    # =====================================================
    # CHECK Y
    # =====================================================

    y_valid = (
        0 <= y < height
    )

    if not y_valid:

        if (
            -VISION_COORDINATE_TOLERANCE
            <= y
            <= (
                height
                - 1
                +
                VISION_COORDINATE_TOLERANCE
            )
        ):

            old_y = y

            y = max(
                0,
                min(
                    y,
                    height - 1
                )
            )

            print(
                "[VISION] "
                f"Koordinat Y boundary dikoreksi: "
                f"{old_y} -> {y}"
            )

        else:

            return _mark_not_found(
                data,
                (
                    f"Koordinat Y vision {y} "
                    f"jauh di luar gambar "
                    f"tinggi {height}."
                )
            )

    data[
        "x"
    ] = x

    data[
        "y"
    ] = y

    return data


# =========================================================
# NORMALIZE JSON MODEL RESPONSE
# =========================================================

def _normalize_json_response(
    raw_content,
    image_path
):
    """
    Semua caller JSON mendapat SATU kontrak:

    - output akhir selalu JSON object valid
    - JSON rusak tidak dilempar ke screen_locate/ui_click
    - output yang tidak bisa diselamatkan -> {}
    """

    data = _loads_relaxed_object(
        raw_content
    )

    if data is None:

        print(
            "[VISION] "
            "Output JSON model tidak valid dan "
            "tidak dapat dinormalisasi -> {}"
        )

        return "{}"

    data = _normalize_boolean_fields(
        data
    )

    data = _normalize_confidence(
        data
    )

    data = _sanitize_vision_coordinates(
        data,
        image_path
    )

    try:

        return json.dumps(
            data,
            ensure_ascii=False
        )

    except (
        TypeError,
        ValueError
    ):

        print(
            "[VISION] "
            "Hasil JSON mengandung nilai yang "
            "tidak serializable -> {}"
        )

        return "{}"


# =========================================================
# FIND LATEST SCREENSHOT
# =========================================================

def get_latest_screenshot():

    if not os.path.isdir(
        SCREENSHOT_DIR
    ):

        raise FileNotFoundError(
            f"Folder screenshot tidak ditemukan: "
            f"{SCREENSHOT_DIR}"
        )

    files = []

    for filename in os.listdir(
        SCREENSHOT_DIR
    ):

        if filename.lower().endswith(
            (
                ".png",
                ".jpg",
                ".jpeg"
            )
        ):

            path = os.path.join(
                SCREENSHOT_DIR,
                filename
            )

            if os.path.isfile(
                path
            ):

                files.append(
                    path
                )

    if not files:

        raise FileNotFoundError(
            "Belum ada screenshot di folder runtime/screenshots."
        )

    return max(
        files,
        key=os.path.getmtime
    )


# =========================================================
# ANALYZE IMAGE
# =========================================================

def analyze_image(
    image_path,
    instruction=None
):

    image_path = os.path.abspath(
        image_path
    )

    if not os.path.isfile(
        image_path
    ):

        raise FileNotFoundError(
            f"Gambar tidak ditemukan: "
            f"{image_path}"
        )

    if instruction is None:

        instruction = """
Analisis screenshot desktop Windows ini.

Sebutkan secara ringkas:
1. Aplikasi/window yang terlihat.
2. Window yang tampaknya aktif.
3. Elemen UI penting yang terlihat.
4. Teks penting yang bisa dibaca.
5. Aktivitas yang kemungkinan sedang dilakukan user.

Jangan mengarang sesuatu yang tidak terlihat.

Gunakan Bahasa Indonesia.
""".strip()

    json_mode = (
        _instruction_requests_json(
            instruction
        )
    )

    # =====================================================
    # EXTRA JSON CONTRACT
    # =====================================================

    if json_mode:

        instruction = (
            instruction.rstrip()
            +
            """

ATURAN OUTPUT TAMBAHAN:
- output wajib SATU JSON object valid
- semua nama key wajib memakai double quote
- string wajib memakai double quote
- boolean harus true atau false
- nilai kosong harus null
- jangan gunakan trailing comma
- jangan tulis komentar
- jangan tulis markdown
- jangan tulis teks sebelum atau sesudah JSON
""".rstrip()
        )

    print(
        "[VISION] Membaca gambar..."
    )

    # =====================================================
    # COMMON CHAT ARGUMENTS
    # =====================================================

    chat_args = {
        "model": VISION_MODEL,

        "messages": [
            {
                "role": "user",

                "content": (
                    instruction
                ),

                "images": [
                    image_path
                ]
            }
        ],

        "options": {
            "temperature": 0.0,

            "num_predict": 500,

            "num_ctx": (
                VISION_CONTEXT
            )
        },

        # Lepaskan model vision dari memory/VRAM
        # setelah request selesai.
        "keep_alive": 0
    }

    # =====================================================
    # FORCE JSON WHEN CALLER REQUESTS JSON
    # =====================================================

    if json_mode:

        chat_args[
            "format"
        ] = "json"

    response = ollama.chat(
        **chat_args
    )

    print(
        "[VISION] Selesai."
    )

    content = str(
        response[
            "message"
        ][
            "content"
        ]
        or ""
    ).strip()

    # =====================================================
    # JSON NORMALIZATION
    # =====================================================

    if json_mode:

        return _normalize_json_response(
            content,
            image_path
        )

    return content


# =========================================================
# ANALYZE LATEST SCREEN
# =========================================================

def analyze_latest_screen(
    instruction=None
):

    image_path = (
        get_latest_screenshot()
    )

    print(
        f"[VISION] Screenshot: "
        f"{image_path}"
    )

    result = analyze_image(
        image_path,
        instruction
    )

    return {
        "path": image_path,
        "analysis": result
    }


# =========================================================
# MANUAL TEST
# =========================================================

if __name__ == "__main__":

    try:

        result = (
            analyze_latest_screen()
        )

        print()

        print(
            "========== HASIL VISION =========="
        )

        print(
            result[
                "analysis"
            ]
        )

        print(
            "=================================="
        )

    except Exception as error:

        print(
            f"[VISION ERROR] {error}"
        )