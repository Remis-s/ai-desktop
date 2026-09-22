import json
import time
import ctypes

from ctypes import wintypes

from vision_runtime import analyze_image

from skills.screen_locate import run as locate_target
from skills.mouse_control import run as mouse_control
from skills.screen_capture import run as screen_capture


# =========================================================
# CONFIG
# =========================================================

DEFAULT_MOVE_DURATION = 0.35

VERIFY_DELAY = 0.8

NAVIGATION_DELAY = 0.7

MAX_NAVIGATION_STEPS = 3

MIN_NAVIGATION_CONFIDENCE = 0.70

MIN_VERIFY_CONFIDENCE = 0.60


# =========================================================
# WIN32
# =========================================================

user32 = ctypes.windll.user32


class RECT(ctypes.Structure):

    _fields_ = [
        (
            "left",
            wintypes.LONG
        ),

        (
            "top",
            wintypes.LONG
        ),

        (
            "right",
            wintypes.LONG
        ),

        (
            "bottom",
            wintypes.LONG
        )
    ]


# =========================================================
# JSON EXTRACTOR
# =========================================================

def _extract_json(text):

    text = str(
        text or ""
    ).strip()

    if text.startswith(
        "```"
    ):

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

        text = "\n".join(
            lines
        ).strip()

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

    try:

        data = json.loads(
            text[
                start:end + 1
            ]
        )

    except json.JSONDecodeError:

        return None

    if not isinstance(
        data,
        dict
    ):

        return None

    return data


# =========================================================
# TEXT NORMALIZATION
# =========================================================

def _normalize_text(text):

    return " ".join(
        str(
            text or ""
        )
        .lower()
        .strip()
        .split()
    )


# =========================================================
# GET WINDOW TITLE
# =========================================================

def _get_window_title(hwnd):

    length = user32.GetWindowTextLengthW(
        hwnd
    )

    if length <= 0:
        return ""

    buffer = ctypes.create_unicode_buffer(
        length + 1
    )

    user32.GetWindowTextW(
        hwnd,
        buffer,
        length + 1
    )

    return buffer.value.strip()


# =========================================================
# GET WINDOW RECT
# =========================================================

def _get_window_rect(hwnd):

    rect = RECT()

    ok = user32.GetWindowRect(
        hwnd,
        ctypes.byref(
            rect
        )
    )

    if not ok:
        return None

    return {
        "x": int(
            rect.left
        ),

        "y": int(
            rect.top
        ),

        "width": int(
            rect.right
            - rect.left
        ),

        "height": int(
            rect.bottom
            - rect.top
        )
    }


# =========================================================
# FIND EXACT HWND
# =========================================================

def _find_matching_hwnd(
    matched_window
):
    """
    Cari HWND yang benar berdasarkan:

    1. title
    2. posisi window
    3. ukuran window

    Jadi dua window dengan title sama
    tetap bisa dibedakan.
    """

    expected_title = str(
        matched_window.get(
            "title",
            ""
        )
    ).strip()

    if not expected_title:
        return None

    expected_x = int(
        matched_window.get(
            "x",
            0
        )
    )

    expected_y = int(
        matched_window.get(
            "y",
            0
        )
    )

    expected_width = int(
        matched_window.get(
            "width",
            0
        )
    )

    expected_height = int(
        matched_window.get(
            "height",
            0
        )
    )

    candidates = []

    ENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HWND,
        wintypes.LPARAM
    )

    def callback(
        hwnd,
        lparam
    ):

        try:

            if not user32.IsWindowVisible(
                hwnd
            ):
                return True

            title = _get_window_title(
                hwnd
            )

            if title != expected_title:
                return True

            rect = _get_window_rect(
                hwnd
            )

            if not rect:
                return True

            # =============================================
            # GEOMETRY DISTANCE
            # =============================================

            score = (
                abs(
                    rect[
                        "x"
                    ]
                    - expected_x
                )
                +
                abs(
                    rect[
                        "y"
                    ]
                    - expected_y
                )
                +
                abs(
                    rect[
                        "width"
                    ]
                    - expected_width
                )
                +
                abs(
                    rect[
                        "height"
                    ]
                    - expected_height
                )
            )

            candidates.append(
                (
                    score,
                    hwnd,
                    rect
                )
            )

        except Exception:
            pass

        return True

    enum_callback = ENUMPROC(
        callback
    )

    user32.EnumWindows(
        enum_callback,
        0
    )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0]
    )

    best_score, hwnd, rect = (
        candidates[0]
    )

    return {
        "hwnd": int(
            hwnd
        ),

        "geometry_score": int(
            best_score
        ),

        "rect": rect
    }


# =========================================================
# CAPTURE TARGET HWND BEFORE CLICK
# =========================================================

def _capture_target_identity(
    locate_result
):

    matched_window = (
        locate_result.get(
            "matched_window"
        )
        or {}
    )

    if not matched_window:
        return None

    result = _find_matching_hwnd(
        matched_window
    )

    if not result:
        return None

    return {
        "hwnd": result[
            "hwnd"
        ],

        "title": matched_window.get(
            "title"
        ),

        "rect": result[
            "rect"
        ],

        "geometry_score": (
            result[
                "geometry_score"
            ]
        ),

        "was_minimized": bool(
            user32.IsIconic(
                result[
                    "hwnd"
                ]
            )
        ),

        "was_maximized": bool(
            user32.IsZoomed(
                result[
                    "hwnd"
                ]
            )
        )
    }


# =========================================================
# VERIFY STANDARD CONTROL BY HWND
# =========================================================

def _verify_standard_control(
    locate_result,
    target_identity
):

    control = str(
        locate_result.get(
            "control",
            ""
        )
    ).lower().strip()

    if not control:

        return {
            "verified": None,

            "method": None,

            "message": (
                "Tidak ada kontrol standar "
                "untuk diverifikasi."
            )
        }

    if not target_identity:

        return {
            "verified": None,

            "method": (
                "hwnd_unavailable"
            ),

            "message": (
                "HWND target tidak berhasil "
                "direkam sebelum klik."
            )
        }

    hwnd = int(
        target_identity[
            "hwnd"
        ]
    )

    # =====================================================
    # CLOSE
    # =====================================================

    if control == "close":

        still_exists = bool(
            user32.IsWindow(
                hwnd
            )
        )

        if not still_exists:

            return {
                "verified": True,

                "method": (
                    "win32_hwnd"
                ),

                "message": (
                    "Window target yang sama "
                    "sudah tidak ada."
                ),

                "hwnd": hwnd
            }

        return {
            "verified": False,

            "method": (
                "win32_hwnd"
            ),

            "message": (
                "Window target yang sama "
                "masih ada setelah klik. "
                "Mungkin muncul dialog konfirmasi "
                "atau aplikasi menolak ditutup."
            ),

            "hwnd": hwnd
        }

    # =====================================================
    # MINIMIZE
    # =====================================================

    if control == "minimize":

        if not user32.IsWindow(
            hwnd
        ):

            return {
                "verified": False,

                "method": (
                    "win32_hwnd"
                ),

                "message": (
                    "Window target menghilang "
                    "setelah klik minimize."
                ),

                "hwnd": hwnd
            }

        minimized = bool(
            user32.IsIconic(
                hwnd
            )
        )

        return {
            "verified": minimized,

            "method": (
                "win32_hwnd"
            ),

            "message": (
                "Window target terdeteksi minimized."
                if minimized
                else
                "Window target belum minimized."
            ),

            "hwnd": hwnd
        }

    # =====================================================
    # MAXIMIZE / RESTORE
    # =====================================================

    if control == "maximize":

        if not user32.IsWindow(
            hwnd
        ):

            return {
                "verified": False,

                "method": (
                    "win32_hwnd"
                ),

                "message": (
                    "Window target tidak ada lagi."
                ),

                "hwnd": hwnd
            }

        now_maximized = bool(
            user32.IsZoomed(
                hwnd
            )
        )

        was_maximized = bool(
            target_identity.get(
                "was_maximized",
                False
            )
        )

        expected = (
            not was_maximized
        )

        return {
            "verified": (
                now_maximized
                ==
                expected
            ),

            "method": (
                "win32_hwnd"
            ),

            "message": (
                f"Maximized sebelum klik: "
                f"{was_maximized}. "
                f"Sesudah klik: "
                f"{now_maximized}. "
                f"Expected: {expected}."
            ),

            "hwnd": hwnd
        }

    return {
        "verified": None,

        "method": None,

        "message": (
            "Kontrol belum memiliki "
            "metode verifikasi."
        )
    }


# =========================================================
# CLICK LOCATED TARGET
# =========================================================

def _click_located_target(
    locate_result,
    move_duration,
    capture_identity=False,
    wait_after=0.0
):

    if not locate_result.get(
        "found",
        False
    ):

        raise RuntimeError(
            "Target belum ditemukan."
        )

    x = locate_result.get(
        "x"
    )

    y = locate_result.get(
        "y"
    )

    if (
        x is None
        or
        y is None
    ):

        raise RuntimeError(
            "Target ditemukan tetapi "
            "koordinat tidak tersedia."
        )

    x = int(
        x
    )

    y = int(
        y
    )

    target_identity = None

    if (
        capture_identity
        and
        locate_result.get(
            "matched_window"
        )
    ):

        target_identity = (
            _capture_target_identity(
                locate_result
            )
        )

        if target_identity:

            print(
                "[UI CLICK] HWND target direkam: "
                f"{target_identity['hwnd']}"
            )

        else:

            print(
                "[UI CLICK] HWND target "
                "tidak berhasil direkam."
            )

    move_result = mouse_control(
        action="move",
        x=x,
        y=y,
        duration=move_duration
    )

    print(
        "[UI CLICK] Mouse diarahkan "
        "ke target."
    )

    time.sleep(
        0.25
    )

    click_result = mouse_control(
        action="click",
        button="left"
    )

    print(
        "[UI CLICK] Target diklik."
    )

    if wait_after > 0:

        time.sleep(
            wait_after
        )

    return {
        "x": x,

        "y": y,

        "target_identity": (
            target_identity
        ),

        "move_result": (
            move_result
        ),

        "click_result": (
            click_result
        )
    }


# =========================================================
# UI NAVIGATION PLANNER
# =========================================================

def _plan_ui_prerequisite(
    final_target,
    locate_result,
    used_targets
):
    """
    Jika target akhir belum terlihat, vision memilih
    SATU kontrol yang benar-benar terlihat dan masuk akal
    untuk membuka target akhir.

    Tidak ada hardcode:

    File -> Save As
    Settings -> Privacy
    dan seterusnya.
    """

    # =====================================================
    # IMPORTANT:
    #
    # Utamakan CROP hasil screen_locate.
    #
    # Dengan begitu planner melihat window target,
    # bukan seluruh desktop berisi VS Code, CMD,
    # ChatGPT, dll.
    # =====================================================

    image_path = (
        locate_result.get(
            "crop_path"
        )
        or
        locate_result.get(
            "path"
        )
    )

    if not image_path:

        capture = screen_capture(
            mode="latest"
        )

        image_path = capture.get(
            "path"
        )

    if not image_path:

        return None

    matched_window = (
        locate_result.get(
            "matched_window"
        )
        or {}
    )

    window_hint = str(
        locate_result.get(
            "window_hint"
        )
        or ""
    ).strip()

    matched_title = str(
        matched_window.get(
            "title",
            ""
        )
    ).strip()

    context_window = (
        window_hint
        or
        matched_title
        or
        "window aktif"
    )

    if used_targets:

        used_text = ", ".join(
            used_targets
        )

    else:

        used_text = (
            "belum ada"
        )

    instruction = f"""
Kamu adalah UI navigation planner untuk desktop Windows.

TUJUAN AKHIR USER:
{final_target}

WINDOW / APLIKASI KONTEKS:
{context_window}

Target akhir saat ini BELUM terlihat.

Gambar yang diberikan berasal dari area window
yang relevan dengan tugas.

Tentukan SATU kontrol UI yang:

1. benar-benar TERLIHAT sekarang
2. berasal dari window/aplikasi yang relevan
3. perlu dibuka agar target akhir nantinya terlihat

Kontrol perantara dapat berupa:

- menu induk
- tab
- dropdown
- tombol tiga titik
- tombol expand
- navigation item
- kategori
- toolbar button
- submenu induk
- tombol pembuka panel

Contoh prinsip:

Jika target akhir merupakan item di dalam sebuah menu,
pilih menu induk yang benar-benar terlihat.

Jika target akhir merupakan pilihan di dalam dropdown,
pilih dropdown yang benar-benar terlihat.

Jika target akhir berada di halaman/kategori lain,
pilih navigation item yang benar-benar terlihat.

SANGAT PENTING:

JANGAN mengarang kontrol yang tidak terlihat.

JANGAN menggunakan tulisan dari prompt sebagai bukti
bahwa kontrol terlihat.

JANGAN memilih area kosong.

JANGAN memilih editor teks/dokumen sebagai kontrol
hanya karena berada di window yang sama.

JANGAN memilih elemen aplikasi lain.

JANGAN memilih target akhir jika target akhir memang
belum terlihat.

JANGAN ulangi kontrol yang sudah dicoba:

{used_text}

Jika tidak ada kontrol perantara yang benar-benar
terlihat dengan cukup yakin:

can_navigate=false

next_target harus berupa nama/deskripsi PENDEK
dari kontrol yang benar-benar terlihat sehingga
bisa diberikan langsung ke screen_locate.

Confidence:

0.0 = tidak yakin
1.0 = sangat yakin

Balas HANYA JSON:

{{
  "can_navigate": true,
  "next_target": "",
  "confidence": 0.0,
  "reason": ""
}}

Jangan gunakan markdown.
Jangan beri teks lain.
""".strip()

    print(
        "[UI NAV] "
        "Vision mencari langkah perantara..."
    )

    try:

        raw = analyze_image(
            image_path,
            instruction
        )

    except Exception as error:

        print(
            "[UI NAV] "
            "Planner vision gagal: "
            f"{error}"
        )

        return None

    data = _extract_json(
        raw
    )

    if not data:
        return None

    if data.get(
        "can_navigate"
    ) is not True:

        return None

    next_target = str(
        data.get(
            "next_target",
            ""
        )
    ).strip()

    if not next_target:
        return None

    try:

        confidence = float(
            data.get(
                "confidence",
                0.0
            )
        )

    except (
        TypeError,
        ValueError
    ):

        confidence = 0.0

    confidence = max(
        0.0,
        min(
            confidence,
            1.0
        )
    )

    if (
        confidence
        <
        MIN_NAVIGATION_CONFIDENCE
    ):

        print(
            "[UI NAV] "
            "Langkah perantara ditolak "
            f"karena confidence="
            f"{confidence:.2f}."
        )

        return None

    normalized_next = (
        _normalize_text(
            next_target
        )
    )

    normalized_final = (
        _normalize_text(
            final_target
        )
    )

    # Planner tidak boleh hanya mengulang
    # target akhir yang memang belum terlihat.
    if (
        normalized_next
        ==
        normalized_final
    ):

        return None

    used_normalized = {
        _normalize_text(
            item
        )
        for item in used_targets
    }

    # Hindari loop.
    if (
        normalized_next
        in
        used_normalized
    ):

        return None

    return {
        "next_target": (
            next_target
        ),

        "confidence": (
            confidence
        ),

        "reason": str(
            data.get(
                "reason",
                ""
            )
        ).strip(),

        "window_hint": (
            window_hint
            or
            matched_title
            or
            None
        )
    }


# =========================================================
# GENERIC VISUAL VERIFICATION
# =========================================================

def _verify_generic_click(
    target,
    locate_result,
    after_path
):
    """
    Untuk elemen UI generik yang tidak punya verifier Win32.

    Vision hanya boleh mengatakan verified=True
    jika benar-benar ada bukti visual setelah klik.
    """

    if not after_path:

        return {
            "verified": None,

            "method": (
                "post_click_vision"
            ),

            "message": (
                "Screenshot setelah klik "
                "tidak tersedia."
            )
        }

    matched_window = (
        locate_result.get(
            "matched_window"
        )
        or {}
    )

    window_title = str(
        matched_window.get(
            "title",
            ""
        )
    ).strip()

    instruction = f"""
Kamu adalah verifier aksi UI desktop Windows.

TARGET YANG BARU DIKLIK:
{target}

WINDOW KONTEKS:
{window_title}

Screenshot ini diambil SETELAH klik.

Tentukan apakah ada BUKTI VISUAL NYATA bahwa
aksi klik menghasilkan perubahan UI yang sesuai.

Contoh bukti:

- menu terbuka
- dropdown terbuka
- submenu muncul
- dialog muncul
- window baru muncul
- halaman berubah
- tab berubah
- panel terbuka
- checkbox berubah
- tombol berubah state
- pilihan menjadi aktif

SANGAT PENTING:

Teks pada ChatGPT, Command Prompt, VS Code,
log program, source code, atau aplikasi lain
yang MENYEBUT nama target BUKAN bukti bahwa
aksi berhasil.

Keberadaan nama target di prompt ini juga
BUKAN bukti.

JANGAN menebak.

Jika bukti keberhasilan jelas:

verified=true

Jika bukti kegagalan jelas:

verified=false

Jika tidak ada bukti visual yang cukup kuat:

verified=null

Balas HANYA JSON:

{{
  "verified": null,
  "confidence": 0.0,
  "evidence": ""
}}

Jangan gunakan markdown.
Jangan beri teks lain.
""".strip()

    print(
        "[UI CLICK] "
        "Memverifikasi hasil klik dengan vision..."
    )

    try:

        raw = analyze_image(
            after_path,
            instruction
        )

    except Exception as error:

        return {
            "verified": None,

            "method": (
                "post_click_vision"
            ),

            "message": (
                "Verifier vision gagal: "
                + str(
                    error
                )
            )
        }

    data = _extract_json(
        raw
    )

    if not data:

        return {
            "verified": None,

            "method": (
                "post_click_vision"
            ),

            "message": (
                "Verifier vision tidak "
                "menghasilkan JSON valid."
            )
        }

    verified = data.get(
        "verified"
    )

    if verified not in (
        True,
        False,
        None
    ):

        verified = None

    try:

        confidence = float(
            data.get(
                "confidence",
                0.0
            )
        )

    except (
        TypeError,
        ValueError
    ):

        confidence = 0.0

    confidence = max(
        0.0,
        min(
            confidence,
            1.0
        )
    )

    if (
        verified is not None
        and
        confidence
        <
        MIN_VERIFY_CONFIDENCE
    ):

        verified = None

    evidence = str(
        data.get(
            "evidence",
            ""
        )
    ).strip()

    return {
        "verified": verified,

        "method": (
            "post_click_vision"
        ),

        "confidence": (
            confidence
        ),

        "message": (
            evidence
            or
            "Tidak ada bukti visual yang cukup jelas."
        )
    }


# =========================================================
# MAIN
# =========================================================

def run(
    target: str,
    verify: bool = True,
    move_duration: float = DEFAULT_MOVE_DURATION,
    navigate: bool = True,
    max_navigation_steps: int = MAX_NAVIGATION_STEPS
):

    target = str(
        target or ""
    ).strip()

    if not target:

        raise ValueError(
            "Target UI belum diberikan."
        )

    # =====================================================
    # NORMALIZE MOVE DURATION
    # =====================================================

    try:

        move_duration = float(
            move_duration
        )

    except (
        TypeError,
        ValueError
    ):

        move_duration = (
            DEFAULT_MOVE_DURATION
        )

    move_duration = max(
        0.0,
        min(
            move_duration,
            3.0
        )
    )

    # =====================================================
    # NORMALIZE MAX NAVIGATION
    # =====================================================

    try:

        max_navigation_steps = int(
            max_navigation_steps
        )

    except (
        TypeError,
        ValueError
    ):

        max_navigation_steps = (
            MAX_NAVIGATION_STEPS
        )

    max_navigation_steps = max(
        0,
        min(
            max_navigation_steps,
            5
        )
    )

    verify = bool(
        verify
    )

    navigate = bool(
        navigate
    )

    # =====================================================
    # 1. INITIAL LOCATE
    # =====================================================

    print(
        f"[UI CLICK] Mencari target: "
        f"{target}"
    )

    # =====================================================
    # PENTING:
    #
    # Percobaan PERTAMA TIDAK BOLEH mencari popup.
    #
    # Kalau target seperti Save As belum terlihat,
    # jangan perluas screenshot lalu membiarkan vision
    # menebak lokasi target.
    #
    # Target harus benar-benar terlihat di window dulu.
    #
    # Kalau tidak terlihat -> masuk UI NAVIGATION.
    # =====================================================

    locate_result = locate_target(
        target=target,
        allow_popup=False
    )

    # =====================================================
    # NAVIGATION HISTORY
    # =====================================================

    navigation_steps = []

    used_navigation_targets = []

    planning_result = (
        locate_result
    )

    # =====================================================
    # 2. HIERARCHICAL UI NAVIGATION
    # =====================================================

    if (
        not locate_result.get(
            "found",
            False
        )
        and
        navigate
        and
        max_navigation_steps > 0
    ):

        for navigation_level in range(
            1,
            max_navigation_steps + 1
        ):

            print(
                "[UI NAV] "
                "Target akhir belum terlihat. "
                f"Navigasi level "
                f"{navigation_level}/"
                f"{max_navigation_steps}."
            )

            # =============================================
            # PLAN NEXT VISIBLE CONTROL
            # =============================================

            navigation_plan = (
                _plan_ui_prerequisite(
                    final_target=target,

                    locate_result=(
                        planning_result
                    ),

                    used_targets=(
                        used_navigation_targets
                    )
                )
            )

            if not navigation_plan:

                print(
                    "[UI NAV] "
                    "Tidak ada kontrol perantara "
                    "yang cukup yakin."
                )

                break

            prerequisite_target = (
                navigation_plan[
                    "next_target"
                ]
            )

            prerequisite_window = (
                navigation_plan.get(
                    "window_hint"
                )
            )

            used_navigation_targets.append(
                prerequisite_target
            )

            print(
                "[UI NAV] "
                f"Kontrol perantara: "
                f"'{prerequisite_target}' "
                f"(confidence="
                f"{navigation_plan['confidence']:.2f})"
            )

            # =============================================
            # LOCATE PREREQUISITE
            # =============================================

            # Level pertama:
            #
            # kontrol perantara harus terlihat langsung
            # di window asli.
            #
            # Level berikutnya:
            #
            # popup/submenu sebelumnya mungkin sudah terbuka,
            # jadi expanded search boleh dipakai.
            prerequisite_allow_popup = (
                navigation_level > 1
            )

            prerequisite_result = (
                locate_target(
                    target=(
                        prerequisite_target
                    ),

                    window_hint=(
                        prerequisite_window
                    ),

                    allow_popup=(
                        prerequisite_allow_popup
                    )
                )
            )

            if not prerequisite_result.get(
                "found",
                False
            ):

                print(
                    "[UI NAV] "
                    "Kontrol perantara tidak "
                    "berhasil dilokalisasi."
                )

                break

            # =============================================
            # CLICK PREREQUISITE
            # =============================================

            try:

                prerequisite_click = (
                    _click_located_target(
                        prerequisite_result,

                        move_duration=(
                            move_duration
                        ),

                        capture_identity=False,

                        wait_after=(
                            NAVIGATION_DELAY
                        )
                    )
                )

            except Exception as error:

                print(
                    "[UI NAV] "
                    "Klik kontrol perantara gagal: "
                    f"{error}"
                )

                break

            navigation_steps.append({
                "level": (
                    navigation_level
                ),

                "target": (
                    prerequisite_target
                ),

                "confidence": (
                    navigation_plan[
                        "confidence"
                    ]
                ),

                "reason": (
                    navigation_plan[
                        "reason"
                    ]
                ),

                "window_hint": (
                    prerequisite_window
                ),

                "x": (
                    prerequisite_click[
                        "x"
                    ]
                ),

                "y": (
                    prerequisite_click[
                        "y"
                    ]
                )
            })

            print(
                "[UI NAV] "
                "Kontrol perantara diklik."
            )

            # =============================================
            # RETRY FINAL TARGET
            # =============================================

            # Sekarang popup/dropdown/submenu boleh dicari
            # karena kita BARU SAJA membuka sebuah kontrol.
            print(
                "[UI NAV] "
                "Mencari target akhir setelah "
                "kontrol perantara dibuka..."
            )

            locate_result = (
                locate_target(
                    target=target,

                    window_hint=(
                        prerequisite_window
                    ),

                    allow_popup=True
                )
            )

            if locate_result.get(
                "found",
                False
            ):

                print(
                    "[UI NAV] "
                    "Target akhir sekarang terlihat."
                )

                break

            # =============================================
            # NEXT NAVIGATION LEVEL
            # =============================================

            # Kalau target akhir masih belum terlihat,
            # gunakan hasil terbaru sebagai bahan planner.
            #
            # Pada tahap ini popup memang sudah nyata
            # karena ada kontrol perantara yang telah diklik.
            planning_result = (
                locate_result
            )

    # =====================================================
    # 3. FINAL TARGET STILL NOT FOUND
    # =====================================================

    if not locate_result.get(
        "found",
        False
    ):

        if navigation_steps:

            raise RuntimeError(
                f"Target '{target}' tidak ditemukan "
                f"setelah mencoba "
                f"{len(navigation_steps)} "
                f"langkah navigasi UI."
            )

        raise RuntimeError(
            f"Target '{target}' "
            f"tidak ditemukan."
        )

    # =====================================================
    # 4. FINAL COORDINATE
    # =====================================================

    x = locate_result.get(
        "x"
    )

    y = locate_result.get(
        "y"
    )

    if (
        x is None
        or
        y is None
    ):

        raise RuntimeError(
            "Target ditemukan tetapi "
            "koordinat tidak tersedia."
        )

    x = int(
        x
    )

    y = int(
        y
    )

    print(
        f"[UI CLICK] Target akhir ditemukan "
        f"di ({x}, {y})."
    )

    # =====================================================
    # 5. FINAL CLICK
    # =====================================================

    final_click = (
        _click_located_target(
            locate_result,

            move_duration=(
                move_duration
            ),

            capture_identity=True,

            wait_after=0.0
        )
    )

    target_identity = (
        final_click[
            "target_identity"
        ]
    )

    move_result = (
        final_click[
            "move_result"
        ]
    )

    click_result = (
        final_click[
            "click_result"
        ]
    )

    # =====================================================
    # 6. WAIT
    # =====================================================

    time.sleep(
        VERIFY_DELAY
    )

    # =====================================================
    # 7. SCREENSHOT AFTER FINAL CLICK
    # =====================================================

    after_capture = screen_capture(
        mode="latest"
    )

    after_path = after_capture.get(
        "path"
    )

    print(
        "[UI CLICK] Screenshot setelah "
        "klik berhasil diambil."
    )

    # =====================================================
    # 8. VERIFY
    # =====================================================

    verification = {
        "verified": None,

        "method": None,

        "message": (
            "Verifikasi tidak diminta."
        )
    }

    if verify:

        control = str(
            locate_result.get(
                "control",
                ""
            )
        )

        source = str(
            locate_result.get(
                "source",
                ""
            )
        )

        # =================================================
        # STANDARD WINDOWS CONTROL
        # =================================================

        if (
            control
            and
            source in {
                "win32_titlebar_info",
                "window_control_geometry_fallback"
            }
        ):

            verification = (
                _verify_standard_control(
                    locate_result,
                    target_identity
                )
            )

        # =================================================
        # GENERIC UI
        # =================================================

        else:

            verification = (
                _verify_generic_click(
                    target=target,

                    locate_result=(
                        locate_result
                    ),

                    after_path=(
                        after_path
                    )
                )
            )

    # =====================================================
    # 9. RESULT MESSAGE
    # =====================================================

    verified_value = (
        verification.get(
            "verified"
        )
    )

    if verified_value is True:

        message = (
            f"Target '{target}' berhasil "
            f"diklik dan hasilnya terverifikasi."
        )

    elif verified_value is False:

        message = (
            f"Target '{target}' sudah diklik, "
            f"tetapi verifikasi menunjukkan "
            f"hasil yang diharapkan belum terjadi."
        )

    else:

        # Jangan mengklaim sukses penuh kalau
        # verifier sendiri tidak mempunyai bukti.
        message = (
            f"Target '{target}' sudah diklik, "
            f"tetapi hasil akhirnya belum "
            f"dapat diverifikasi."
        )

    # =====================================================
    # RESULT
    # =====================================================

    return {
        "message": (
            message
        ),

        "target": (
            target
        ),

        "x": (
            x
        ),

        "y": (
            y
        ),

        "locator_source": (
            locate_result.get(
                "source"
            )
        ),

        "locator_crop_mode": (
            locate_result.get(
                "crop_mode"
            )
        ),

        "locator_attempted_crop_modes": (
            locate_result.get(
                "attempted_crop_modes"
            )
        ),

        "confidence": (
            locate_result.get(
                "confidence"
            )
        ),

        "target_hwnd": (
            target_identity.get(
                "hwnd"
            )
            if target_identity
            else None
        ),

        "navigation_used": bool(
            navigation_steps
        ),

        "navigation_steps": (
            navigation_steps
        ),

        "move_result": (
            move_result
        ),

        "click_result": (
            click_result
        ),

        "verification": (
            verification
        ),

        "after_screenshot": (
            after_path
        )
    }


# =========================================================
# TOOL
# =========================================================

TOOL = {
    "name": "ui_click",

    "description": (
        "Mencari dan mengklik elemen UI pada desktop Windows. "
        "Menggunakan screen_locate untuk localization. "
        "Pencarian awal hanya menerima elemen yang benar-benar "
        "terlihat pada window konteks dan tidak langsung mencari "
        "popup tersembunyi. "
        "Jika target akhir belum terlihat, tool dapat melakukan "
        "navigasi UI bertingkat secara otomatis dengan mencari "
        "kontrol perantara yang benar-benar terlihat seperti "
        "menu induk, tab, dropdown, submenu, tombol expand, "
        "tombol tiga titik, navigation item, atau kategori. "
        "Popup, dropdown, submenu, flyout, dan overlay baru "
        "diizinkan setelah sebuah kontrol perantara benar-benar "
        "diklik. "
        "Setelah kontrol perantara diklik, screenshot diperbarui "
        "dan target akhir dicari kembali. "
        "Untuk Close, Minimize, dan Maximize standar Windows, "
        "window target direkam dengan HWND agar verifikasi tetap "
        "membedakan window yang judulnya sama. "
        "Untuk elemen UI generik, hasil klik diverifikasi "
        "dengan vision dari screenshot setelah aksi."
    ),

    "parameters": {
        "target": {
            "type": "string",

            "description": (
                "Target akhir yang ingin diklik. "
                "Contoh: 'menu File di Notepad', "
                "'Save As di Notepad', "
                "'Privacy di Settings', "
                "atau 'tombol Close X pada jendela Notepad'."
            )
        },

        "verify": {
            "type": "boolean",

            "description": (
                "Verifikasi hasil setelah klik. "
                "Default true."
            )
        },

        "move_duration": {
            "type": "number",

            "description": (
                "Durasi perpindahan mouse. "
                "Default 0.35 detik."
            )
        },

        "navigate": {
            "type": "boolean",

            "description": (
                "Jika target belum terlihat, izinkan "
                "navigasi UI bertingkat otomatis. "
                "Default true."
            )
        },

        "max_navigation_steps": {
            "type": "integer",

            "description": (
                "Jumlah maksimal kontrol perantara "
                "yang boleh diklik sebelum menyerah. "
                "Default 3, maksimal 5."
            )
        }
    },

    "run": run
}