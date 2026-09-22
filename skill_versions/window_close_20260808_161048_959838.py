from skills.ui_click import run as ui_click


def run(
    title=None,
    window_title=None,
    target=None,
    verify=True
):
    """
    Menutup window tertentu menggunakan ui_click.

    Mendukung beberapa nama parameter supaya agent
    lebih fleksibel:
    - title
    - window_title
    - target
    """

    # =====================================================
    # RESOLVE WINDOW NAME
    # =====================================================

    name = (
        title
        or window_title
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
    # CLEAN COMMON PREFIXES
    # =====================================================

    lowered = name.lower()

    prefixes = (
        "jendela ",
        "window ",
        "aplikasi "
    )

    for prefix in prefixes:
        if lowered.startswith(prefix):

            name = name[
                len(prefix):
            ].strip()

            break

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

    verification = (
        result.get(
            "verification",
            {}
        )
    )

    verified = (
        verification.get(
            "verified"
        )
    )

    if verified is True:

        message = (
            f"Jendela '{name}' berhasil ditutup "
            f"dan sudah diverifikasi."
        )

    elif verified is False:

        message = (
            f"Klik Close pada jendela '{name}' sudah dilakukan, "
            f"tetapi window masih terdeteksi."
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


TOOL = {
    "name": "window_close",

    "description": (
        "Menutup jendela aplikasi Windows tertentu. "
        "Gunakan tool ini jika user mengatakan tutup, close, "
        "keluar dari, atau menutup suatu jendela aplikasi. "
        "Tool menggunakan screen_locate, koordinat Win32, "
        "mouse click, HWND, dan verifikasi melalui ui_click. "
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
                "Alternatif parameter untuk nama window."
            )
        },

        "target": {
            "type": "string",

            "description": (
                "Alternatif parameter untuk nama window."
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