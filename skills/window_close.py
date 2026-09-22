from skills.ui_click import run as ui_click


# =========================================================
# MAIN
# =========================================================

def run(
    title=None,
    window_title=None,
    window_name=None,
    target=None,
    verify=True
):
    """
    Menutup window tertentu menggunakan ui_click.

    Parameter utama:
    - title

    Alias yang juga diterima:
    - window_title
    - window_name
    - target
    """

    # =====================================================
    # RESOLVE WINDOW NAME
    # =====================================================

    name = (
        title
        or window_title
        or window_name
        or target
        or ""
    )

    name = str(
        name
    ).strip()

    if not name:
        raise ValueError(
            "Nama window yang ingin ditutup belum diberikan."
        )

    # =====================================================
    # CLEAN PUNCTUATION
    # =====================================================

    name = name.strip(
        " \t\r\n.,!?;:\"'"
    )

    # =====================================================
    # CLEAN COMMON PREFIXES
    # =====================================================

    lowered = name.lower()

    prefixes = (
        "jendela ",
        "window ",
        "aplikasi "
    )

    for prefix in prefixes:

        if lowered.startswith(
            prefix
        ):

            name = name[
                len(prefix):
            ].strip()

            break

    # =====================================================
    # CLEAN COMMON SUFFIXES
    # =====================================================

    # Ulangi supaya:
    #
    # "Notepad yang terbuka."
    #
    # menjadi:
    #
    # "Notepad"

    name = name.strip(
        " \t\r\n.,!?;:\"'"
    )

    lowered = name.lower()

    suffixes = (
        " yang sedang terbuka",
        " yang terbuka",
        " yang sedang aktif",
        " yang aktif"
    )

    for suffix in suffixes:

        if lowered.endswith(
            suffix
        ):

            name = name[
                :len(name) - len(suffix)
            ].strip()

            break

    # =====================================================
    # CLEAN CASUAL TRAILING WORDS
    # =====================================================

    name = name.strip(
        " \t\r\n.,!?;:\"'"
    )

    lowered = name.lower()

    casual_suffixes = (
        " dong",
        " sekarang",
        " ya",
        " yah",
        " deh"
    )

    for suffix in casual_suffixes:

        if lowered.endswith(
            suffix
        ):

            name = name[
                :len(name) - len(suffix)
            ].strip()

            break

    name = name.strip(
        " \t\r\n.,!?;:\"'"
    )

    if not name:
        raise ValueError(
            "Nama window tidak valid."
        )

    # =====================================================
    # BUILD UI TARGET
    # =====================================================

    visual_target = (
        f"tombol Close X pada jendela {name}"
    )

    print(
        f"[WINDOW CLOSE] Menutup: {name}"
    )

    # =====================================================
    # USE EXISTING VERIFIED PIPELINE
    # =====================================================

    result = ui_click(
        target=visual_target,
        verify=bool(verify)
    )

    verification = result.get(
        "verification",
        {}
    )

    if not isinstance(
        verification,
        dict
    ):
        verification = {}

    verified = verification.get(
        "verified"
    )

    # =====================================================
    # RESULT MESSAGE
    # =====================================================

    if verified is True:

        message = (
            f"Jendela '{name}' berhasil ditutup "
            f"dan sudah diverifikasi."
        )

    elif verified is False:

        message = (
            f"Klik Close pada jendela '{name}' sudah dilakukan, "
            f"tetapi window target masih terdeteksi."
        )

    else:

        message = (
            f"Klik Close pada jendela '{name}' sudah dilakukan, "
            f"tetapi hasilnya belum dapat diverifikasi."
        )

    return {
        "message": message,

        "window": name,

        "verified": verified,

        "verification": verification,

        "ui_click_result": result
    }


# =========================================================
# TOOL
# =========================================================

TOOL = {
    "name": "window_close",

    "description": (
        "Menutup jendela aplikasi Windows tertentu. "
        "Gunakan tool ini jika user mengatakan tutup, close, "
        "keluar dari, atau menutup suatu jendela aplikasi. "
        "Tool menggunakan screen_locate, koordinat Win32, "
        "mouse click, HWND, dan verifikasi melalui ui_click. "
        "Parameter utama adalah 'title'. "
        "Alias window_title, window_name, dan target juga diterima. "
        "Jangan membuat skill baru jika tool ini tersedia."
    ),

    "parameters": {
        "title": {
            "type": "string",
            "description": (
                "Nama atau judul window yang ingin ditutup. "
                "Contoh: 'Notepad', 'Untitled - Notepad', "
                "'Google Chrome'."
            )
        },

        "window_title": {
            "type": "string",
            "description": (
                "Alias untuk title."
            )
        },

        "window_name": {
            "type": "string",
            "description": (
                "Alias untuk title. "
                "Contoh: 'Notepad'."
            )
        },

        "target": {
            "type": "string",
            "description": (
                "Alias untuk title."
            )
        },

        "verify": {
            "type": "boolean",
            "description": (
                "Verifikasi bahwa window target benar-benar "
                "tertutup. Default true."
            )
        }
    },

    "run": run
}