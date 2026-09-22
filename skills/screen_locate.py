import json
import os
import re
import ctypes

from ctypes import wintypes
from difflib import SequenceMatcher

from PIL import Image

from vision_runtime import analyze_image
from skills.screen_capture import run as screen_capture_run
from skills.screen_state import run as screen_state_run


# =========================================================
# CONFIG
# =========================================================

MIN_CONFIDENCE = 0.55

# Second-pass hanya memastikan target memang terlihat.
# Tidak lagi memakai crosshair.
MIN_VISIBILITY_CONFIDENCE = 0.60

# Retry hanya untuk output vision rusak / kandidat meragukan.
MAX_LOCALIZATION_ATTEMPTS = 2


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

CROP_PATH = os.path.join(
    SCREENSHOT_DIR,
    "locate_crop.png"
)


# =========================================================
# TEXT NORMALIZATION
# =========================================================

def _normalize_text(text):

    text = str(
        text or ""
    ).lower()

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text
    )

    return " ".join(
        text.split()
    )


def _clean_text_end(text):

    return str(
        text or ""
    ).strip(
        " \t\r\n.,!?;:\"'"
    )


# =========================================================
# KNOWN TERMINAL / SHELL TITLES
# =========================================================

SHELL_IDENTITIES = {
    "command prompt": (
        "command prompt",
        "cmd"
    ),

    "windows powershell": (
        "windows powershell",
        "powershell"
    ),

    "powershell": (
        "powershell",
    ),

    "windows terminal": (
        "windows terminal",
        "terminal"
    )
}


def _detect_shell_identity(title):

    raw_title = str(
        title or ""
    ).strip()

    title_lower = raw_title.lower()

    title_norm = _normalize_text(
        raw_title
    )

    cmd_markers = (
        "command prompt",
        "cmd.exe",
        "\\cmd.exe",
        "/cmd.exe",
        "system32\\cmd.exe"
    )

    if any(
        marker in title_lower
        for marker in cmd_markers
    ):
        return "command prompt"

    powershell_markers = (
        "windows powershell",
        "powershell.exe",
        "\\powershell.exe",
        "/powershell.exe"
    )

    if any(
        marker in title_lower
        for marker in powershell_markers
    ):
        return "windows powershell"

    pwsh_markers = (
        "pwsh.exe",
        "\\pwsh.exe",
        "/pwsh.exe"
    )

    if any(
        marker in title_lower
        for marker in pwsh_markers
    ):
        return "powershell"

    terminal_markers = (
        "windows terminal",
        "wt.exe",
        "\\wt.exe",
        "/wt.exe"
    )

    if any(
        marker in title_lower
        for marker in terminal_markers
    ):
        return "windows terminal"

    for shell_name in SHELL_IDENTITIES:

        if (
            title_norm == shell_name
            or
            title_norm.startswith(
                shell_name + " "
            )
        ):
            return shell_name

    return None


# =========================================================
# SAFE WINDOW IDENTITY CANDIDATES
# =========================================================

def _window_identity_candidates(title):

    title = str(
        title or ""
    ).strip()

    if not title:
        return []

    shell_identity = (
        _detect_shell_identity(
            title
        )
    )

    if shell_identity:

        aliases = (
            SHELL_IDENTITIES[
                shell_identity
            ]
        )

        return [
            _normalize_text(
                item
            )
            for item in aliases
        ]

    candidates = []

    full_title = _normalize_text(
        title
    )

    if full_title:

        candidates.append(
            full_title
        )

    segments = [
        _normalize_text(
            item
        )
        for item in title.split(
            " - "
        )
    ]

    for segment in segments:

        if (
            segment
            and
            segment not in candidates
        ):

            candidates.append(
                segment
            )

    return candidates


# =========================================================
# UI TARGET / WINDOW CONTEXT PARSER
# =========================================================

SPATIAL_CONTEXT_WORDS = {
    "kanan",
    "kiri",
    "atas",
    "bawah",
    "tengah",
    "pojok",
    "samping",
    "sebelah",
    "dekat"
}


def _clean_window_hint(text):

    text = _clean_text_end(
        text
    )

    text = re.sub(
        r"^(?:jendela|window|aplikasi|application|app)\s+",
        "",
        text,
        flags=re.IGNORECASE
    ).strip()

    text = re.sub(
        r"\s+yang\s+(?:sedang\s+)?terbuka\s*$",
        "",
        text,
        flags=re.IGNORECASE
    ).strip()

    text = re.sub(
        r"\s+yang\s+(?:sedang\s+)?aktif\s*$",
        "",
        text,
        flags=re.IGNORECASE
    ).strip()

    return _clean_text_end(
        text
    )


def _parse_target_context(target):

    raw = _clean_text_end(
        target
    )

    if not raw:

        return {
            "element_target": "",
            "window_hint": None,
            "explicit_window": False
        }

    normalized = _normalize_text(
        raw
    )

    # =====================================================
    # WHOLE WINDOW
    # =====================================================

    if (
        normalized.startswith(
            "jendela "
        )
        or
        normalized.startswith(
            "window "
        )
    ):

        return {
            "element_target": raw,
            "window_hint": None,
            "explicit_window": False
        }

    # =====================================================
    # EXPLICIT WINDOW CONTEXT
    # =====================================================

    explicit_match = re.match(
        r"^(.+?)\s+"
        r"(?:di|pada|dalam)\s+"
        r"(?:jendela|window|aplikasi|application|app)\s+"
        r"(.+)$",
        raw,
        flags=re.IGNORECASE
    )

    if explicit_match:

        element_target = (
            _clean_text_end(
                explicit_match.group(
                    1
                )
            )
        )

        window_hint = (
            _clean_window_hint(
                explicit_match.group(
                    2
                )
            )
        )

        if (
            element_target
            and
            window_hint
        ):

            return {
                "element_target": element_target,
                "window_hint": window_hint,
                "explicit_window": True
            }

    # =====================================================
    # NATURAL WINDOW CONTEXT
    # =====================================================

    natural_match = re.match(
        r"^(.+?)\s+"
        r"(?:di|pada|dalam)\s+"
        r"(.+)$",
        raw,
        flags=re.IGNORECASE
    )

    if natural_match:

        left = _clean_text_end(
            natural_match.group(
                1
            )
        )

        right = _clean_window_hint(
            natural_match.group(
                2
            )
        )

        right_tokens = set(
            _normalize_text(
                right
            ).split()
        )

        contains_spatial_hint = bool(
            right_tokens
            &
            SPATIAL_CONTEXT_WORDS
        )

        right_word_count = len(
            right_tokens
        )

        if (
            left
            and
            right
            and
            not contains_spatial_hint
            and
            right_word_count <= 8
        ):

            return {
                "element_target": left,
                "window_hint": right,
                "explicit_window": True
            }

    return {
        "element_target": raw,
        "window_hint": None,
        "explicit_window": False
    }


# =========================================================
# WINDOW MATCHING
# =========================================================

WINDOW_STOPWORDS = {
    "tombol",
    "button",
    "ikon",
    "icon",
    "menu",
    "kolom",
    "field",
    "textbox",

    "pada",
    "di",
    "dalam",
    "dari",

    "jendela",
    "window",
    "aplikasi",
    "app",

    "close",
    "tutup",

    "minimize",
    "minimise",
    "minimalkan",

    "maximize",
    "maximise",
    "maksimalkan",

    "restore",

    "save",

    "x"
}


GENERIC_UI_LABELS = {
    "file",
    "edit",
    "view",
    "help",
    "save",
    "open",
    "new",
    "home",
    "back",
    "next",
    "search",
    "settings",
    "ok",
    "cancel",
    "yes",
    "no",
    "copy",
    "paste",
    "cut",
    "undo",
    "redo"
}


def _tokens(text):

    return {
        token
        for token in _normalize_text(
            text
        ).split()
        if (
            len(token) > 1
            and
            token not in WINDOW_STOPWORDS
        )
    }


def _window_match_score(
    target,
    title
):

    target_norm = _normalize_text(
        target
    )

    if not target_norm:
        return 0.0

    candidates = (
        _window_identity_candidates(
            title
        )
    )

    if not candidates:
        return 0.0

    target_tokens = _tokens(
        target
    )

    raw_target_tokens = set(
        target_norm.split()
    )

    single_generic_target = (
        len(raw_target_tokens) == 1
        and
        next(
            iter(
                raw_target_tokens
            ),
            ""
        )
        in GENERIC_UI_LABELS
    )

    best_score = 0.0

    for candidate in candidates:

        if not candidate:
            continue

        candidate_tokens = _tokens(
            candidate
        )

        # =================================================
        # EXACT
        # =================================================

        if candidate == target_norm:

            exact_score = (
                0.55
                if single_generic_target
                else 1.0
            )

            best_score = max(
                best_score,
                exact_score
            )

        # =================================================
        # CANDIDATE INSIDE TARGET
        # =================================================

        elif candidate in target_norm:

            best_score = max(
                best_score,
                0.98
            )

        # =================================================
        # TARGET INSIDE WINDOW TITLE
        # =================================================

        elif (
            target_norm in candidate
            and
            not single_generic_target
            and
            len(target_norm) >= 4
        ):

            best_score = max(
                best_score,
                0.90
            )

        # =================================================
        # TOKEN OVERLAP
        # =================================================

        if (
            target_tokens
            and
            candidate_tokens
        ):

            overlap = (
                target_tokens
                &
                candidate_tokens
            )

            union = (
                target_tokens
                |
                candidate_tokens
            )

            if overlap and union:

                overlap_score = (
                    len(overlap)
                    /
                    len(union)
                )

                if single_generic_target:

                    overlap_score = min(
                        overlap_score,
                        0.40
                    )

                best_score = max(
                    best_score,
                    overlap_score
                )

        # =================================================
        # FUZZY
        # =================================================

        similarity = (
            SequenceMatcher(
                None,
                target_norm,
                candidate
            ).ratio()
        )

        fuzzy_score = (
            similarity
            *
            0.70
        )

        if single_generic_target:

            fuzzy_score = min(
                fuzzy_score,
                0.40
            )

        best_score = max(
            best_score,
            fuzzy_score
        )

    return best_score


def _find_best_window(
    target,
    windows,
    minimum_score=0.45
):

    best_window = None
    best_score = 0.0

    for window in windows:

        title = str(
            window.get(
                "title",
                ""
            )
        ).strip()

        if not title:
            continue

        score = (
            _window_match_score(
                target,
                title
            )
        )

        if window.get(
            "minimized",
            False
        ):

            score *= 0.85

        if score > best_score:

            best_score = score
            best_window = window

    if best_score < minimum_score:

        return (
            None,
            best_score
        )

    return (
        best_window,
        best_score
    )


# =========================================================
# TARGET TYPE
# =========================================================

UI_ELEMENT_HINTS = (
    "tombol",
    "button",

    "ikon",
    "icon",

    "menu",

    "kolom",
    "field",
    "textbox",

    "search",
    "pencarian",

    "save",

    "tab",
    "checkbox",
    "dropdown",

    "alamat",
    "address",

    "link",

    "toolbar",
    "ribbon"
)


def _target_has_ui_hint(
    target
):

    text = _normalize_text(
        target
    )

    return any(
        hint in text
        for hint in UI_ELEMENT_HINTS
    )


def _is_generic_ui_label(
    target
):

    tokens = _normalize_text(
        target
    ).split()

    if len(tokens) != 1:
        return False

    return (
        tokens[0]
        in
        GENERIC_UI_LABELS
    )


def _is_whole_window_target(
    target
):

    text = _normalize_text(
        target
    )

    has_window_word = (
        "jendela" in text
        or
        "window" in text
    )

    has_ui_element = any(
        hint in text
        for hint in UI_ELEMENT_HINTS
    )

    return (
        has_window_word
        and
        not has_ui_element
    )


# =========================================================
# STANDARD WINDOW CONTROLS
# =========================================================

def _detect_standard_window_control(
    target
):

    text = _normalize_text(
        target
    )

    close_patterns = (
        "close",
        "tutup",
        "tombol x",
        "button x"
    )

    if any(
        pattern in text
        for pattern in close_patterns
    ):
        return "close"

    maximize_patterns = (
        "maximize",
        "maximise",
        "maksimalkan",
        "maximize button",
        "restore",
        "restore down"
    )

    if any(
        pattern in text
        for pattern in maximize_patterns
    ):
        return "maximize"

    minimize_patterns = (
        "minimize",
        "minimise",
        "minimalkan",
        "minimize button"
    )

    if any(
        pattern in text
        for pattern in minimize_patterns
    ):
        return "minimize"

    return None


# =========================================================
# CROP TARGET MODE
# =========================================================

TITLEBAR_HINTS = (
    "close",
    "tutup",
    "tombol x",

    "minimize",
    "minimise",
    "minimalkan",

    "maximize",
    "maximise",
    "maksimalkan",

    "restore",

    "titlebar",
    "title bar"
)


TOP_UI_HINTS = (
    "menu",
    "tab",
    "toolbar",
    "ribbon",
    "address",
    "alamat",
    "breadcrumb"
)


def _is_titlebar_target(
    target
):

    text = _normalize_text(
        target
    )

    return any(
        hint in text
        for hint in TITLEBAR_HINTS
    )


def _crop_mode_for_target(
    target
):

    text = _normalize_text(
        target
    )

    if _is_titlebar_target(
        target
    ):

        return "titlebar"

    # File/Edit/View/Help dan label UI pendek lebih baik
    # difokuskan ke area atas window.
    if _is_generic_ui_label(
        target
    ):

        return "top_ui"

    if any(
        hint in text
        for hint in TOP_UI_HINTS
    ):

        return "top_ui"

    return "full"


# =========================================================
# ACTIVE WINDOW
# =========================================================

def _active_window_from_state(
    state
):

    active = state.get(
        "active_window"
    )

    if not isinstance(
        active,
        dict
    ):

        return None

    title = str(
        active.get(
            "title",
            ""
        )
    ).strip()

    if not title:
        return None

    return active


# =========================================================
# WIN32 WINDOW LOOKUP
# =========================================================

def _find_hwnd_by_title(
    expected_title
):

    expected_title = str(
        expected_title or ""
    ).strip()

    if not expected_title:
        return None

    user32 = (
        ctypes.windll.user32
    )

    found = []

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

            length = (
                user32.GetWindowTextLengthW(
                    hwnd
                )
            )

            if length <= 0:
                return True

            buffer = (
                ctypes.create_unicode_buffer(
                    length + 1
                )
            )

            user32.GetWindowTextW(
                hwnd,
                buffer,
                length + 1
            )

            title = (
                buffer.value.strip()
            )

            if title == expected_title:

                found.append(
                    hwnd
                )

                return False

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

    if found:
        return found[0]

    return None


# =========================================================
# WIN32 TITLEBAR INFO
# =========================================================

def _get_win32_caption_control_rect(
    window_title,
    control_name
):

    hwnd = _find_hwnd_by_title(
        window_title
    )

    if not hwnd:
        return None

    class RECT(
        ctypes.Structure
    ):

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

    CHILD_COUNT = 6

    class TITLEBARINFOEX(
        ctypes.Structure
    ):

        _fields_ = [
            (
                "cbSize",
                wintypes.DWORD
            ),
            (
                "rcTitleBar",
                RECT
            ),
            (
                "rgstate",
                wintypes.DWORD
                *
                CHILD_COUNT
            ),
            (
                "rgrect",
                RECT
                *
                CHILD_COUNT
            )
        ]

    indexes = {
        "minimize": 2,
        "maximize": 3,
        "close": 5
    }

    index = indexes.get(
        control_name
    )

    if index is None:
        return None

    WM_GETTITLEBARINFOEX = (
        0x033F
    )

    user32 = (
        ctypes.windll.user32
    )

    info = TITLEBARINFOEX()

    info.cbSize = ctypes.sizeof(
        TITLEBARINFOEX
    )

    try:

        user32.SendMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            ctypes.c_ssize_t
        ]

        user32.SendMessageW.restype = (
            ctypes.c_ssize_t
        )

        user32.SendMessageW(
            hwnd,
            WM_GETTITLEBARINFOEX,
            0,
            ctypes.addressof(
                info
            )
        )

    except Exception:
        return None

    rect = (
        info.rgrect[
            index
        ]
    )

    left = int(
        rect.left
    )

    top = int(
        rect.top
    )

    right = int(
        rect.right
    )

    bottom = int(
        rect.bottom
    )

    if (
        right <= left
        or
        bottom <= top
    ):

        return None

    STATE_SYSTEM_INVISIBLE = (
        0x00008000
    )

    state = int(
        info.rgstate[
            index
        ]
    )

    if (
        state
        &
        STATE_SYSTEM_INVISIBLE
    ):

        return None

    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,

        "x": round(
            (
                left
                +
                right
            )
            / 2
        ),

        "y": round(
            (
                top
                +
                bottom
            )
            / 2
        ),

        "width": (
            right
            -
            left
        ),

        "height": (
            bottom
            -
            top
        ),

        "hwnd": int(
            hwnd
        )
    }


# =========================================================
# FALLBACK CAPTION GEOMETRY
# =========================================================

def _caption_control_geometry_fallback(
    window,
    control_name,
    screen_width,
    screen_height
):

    user32 = (
        ctypes.windll.user32
    )

    try:

        metric_width = int(
            user32.GetSystemMetrics(
                30
            )
        )

        metric_height = int(
            user32.GetSystemMetrics(
                31
            )
        )

    except Exception:

        metric_width = 46
        metric_height = 30

    button_width = max(
        metric_width,
        40
    )

    button_height = max(
        metric_height,
        28
    )

    window_x = int(
        window.get(
            "x",
            0
        )
    )

    window_y = int(
        window.get(
            "y",
            0
        )
    )

    window_width = int(
        window.get(
            "width",
            0
        )
    )

    right_edge = (
        window_x
        +
        window_width
    )

    if control_name == "close":

        x = (
            right_edge
            -
            (
                button_width
                / 2
            )
        )

    elif control_name == "maximize":

        x = (
            right_edge
            -
            (
                button_width
                * 1.5
            )
        )

    elif control_name == "minimize":

        x = (
            right_edge
            -
            (
                button_width
                * 2.5
            )
        )

    else:
        return None

    y = (
        window_y
        +
        (
            button_height
            / 2
        )
    )

    x = round(
        x
    )

    y = round(
        y
    )

    x = max(
        0,
        min(
            x,
            screen_width - 1
        )
    )

    y = max(
        0,
        min(
            y,
            screen_height - 1
        )
    )

    return {
        "x": x,
        "y": y,
        "width": button_width,
        "height": button_height
    }


# =========================================================
# LOCATE STANDARD WINDOW CONTROL
# =========================================================

def _locate_standard_window_control(
    window,
    control_name,
    screen_width,
    screen_height
):

    title = str(
        window.get(
            "title",
            ""
        )
    )

    win32_rect = (
        _get_win32_caption_control_rect(
            title,
            control_name
        )
    )

    if win32_rect:

        x = max(
            0,
            min(
                int(
                    win32_rect[
                        "x"
                    ]
                ),
                screen_width - 1
            )
        )

        y = max(
            0,
            min(
                int(
                    win32_rect[
                        "y"
                    ]
                ),
                screen_height - 1
            )
        )

        return {
            "x": x,
            "y": y,

            "confidence": 1.0,

            "source": (
                "win32_titlebar_info"
            ),

            "control_rect": {
                "left": (
                    win32_rect[
                        "left"
                    ]
                ),

                "top": (
                    win32_rect[
                        "top"
                    ]
                ),

                "right": (
                    win32_rect[
                        "right"
                    ]
                ),

                "bottom": (
                    win32_rect[
                        "bottom"
                    ]
                ),

                "width": (
                    win32_rect[
                        "width"
                    ]
                ),

                "height": (
                    win32_rect[
                        "height"
                    ]
                )
            }
        }

    fallback = (
        _caption_control_geometry_fallback(
            window,
            control_name,
            screen_width,
            screen_height
        )
    )

    if not fallback:
        return None

    return {
        "x": fallback[
            "x"
        ],

        "y": fallback[
            "y"
        ],

        "confidence": 0.80,

        "source": (
            "window_control_geometry_fallback"
        ),

        "control_rect": None
    }


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

        lines = (
            text.splitlines()
        )

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

        raise ValueError(
            "Vision tidak menghasilkan JSON."
        )

    try:

        data = json.loads(
            text[
                start:end + 1
            ]
        )

    except json.JSONDecodeError as error:

        raise ValueError(
            f"JSON vision tidak valid: "
            f"{error}"
        )

    if not isinstance(
        data,
        dict
    ):

        raise ValueError(
            "Output vision harus object JSON."
        )

    return data


# =========================================================
# DESCRIPTION POSITION VALIDATION
# =========================================================

def _description_position_matches(
    description,
    x,
    y,
    width,
    height
):

    text = _normalize_text(
        description
    )

    if not text:
        return True

    relative_x = (
        x
        /
        max(
            width,
            1
        )
    )

    relative_y = (
        y
        /
        max(
            height,
            1
        )
    )

    if (
        "kanan" in text
        and
        relative_x < 0.45
    ):
        return False

    if (
        "kiri" in text
        and
        relative_x > 0.55
    ):
        return False

    if (
        "atas" in text
        and
        relative_y > 0.70
    ):
        return False

    if (
        "bawah" in text
        and
        relative_y < 0.30
    ):
        return False

    return True


# =========================================================
# NUMBER PARSER
# =========================================================

def _to_number(value):

    if isinstance(
        value,
        bool
    ):

        raise ValueError(
            "Boolean bukan koordinat."
        )

    return float(
        value
    )


# =========================================================
# CANDIDATE COORDINATE PARSER
# =========================================================

def _extract_candidate_coordinates(
    data,
    width,
    height
):
    """
    Prioritas:

    1. Bounding box.
    2. x/y.

    Kalau bbox tersedia, titik klik dihitung sendiri
    dari titik tengah bbox.
    """

    bbox_keys = (
        "left",
        "top",
        "right",
        "bottom"
    )

    if all(
        data.get(
            key
        ) is not None
        for key in bbox_keys
    ):

        try:

            left = _to_number(
                data.get(
                    "left"
                )
            )

            top = _to_number(
                data.get(
                    "top"
                )
            )

            right = _to_number(
                data.get(
                    "right"
                )
            )

            bottom = _to_number(
                data.get(
                    "bottom"
                )
            )

            if (
                right > left
                and
                bottom > top
            ):

                left = max(
                    0.0,
                    min(
                        left,
                        width - 1
                    )
                )

                top = max(
                    0.0,
                    min(
                        top,
                        height - 1
                    )
                )

                right = max(
                    left + 1.0,
                    min(
                        right,
                        width
                    )
                )

                bottom = max(
                    top + 1.0,
                    min(
                        bottom,
                        height
                    )
                )

                x = round(
                    (
                        left
                        +
                        right
                    )
                    / 2
                )

                y = round(
                    (
                        top
                        +
                        bottom
                    )
                    / 2
                )

                x = max(
                    0,
                    min(
                        x,
                        width - 1
                    )
                )

                y = max(
                    0,
                    min(
                        y,
                        height - 1
                    )
                )

                return (
                    x,
                    y,
                    {
                        "left": round(
                            left
                        ),
                        "top": round(
                            top
                        ),
                        "right": round(
                            right
                        ),
                        "bottom": round(
                            bottom
                        )
                    }
                )

        except (
            TypeError,
            ValueError
        ):
            pass

    raw_x = data.get(
        "x"
    )

    raw_y = data.get(
        "y"
    )

    if (
        raw_x is None
        or
        raw_y is None
    ):

        raise ValueError(
            "Vision mengatakan target ditemukan "
            "tetapi koordinat kosong."
        )

    x = round(
        _to_number(
            raw_x
        )
    )

    y = round(
        _to_number(
            raw_y
        )
    )

    # Model kadang memberi tepat width/height.
    # Perlakukan sebagai pixel paling pinggir.
    if x == width:
        x = width - 1

    if y == height:
        y = height - 1

    if not (
        0 <= x < width
        and
        0 <= y < height
    ):

        raise ValueError(
            f"Koordinat vision "
            f"({x},{y}) "
            f"di luar gambar "
            f"{width}x{height}."
        )

    return (
        x,
        y,
        None
    )


# =========================================================
# TARGET VISIBILITY VERIFIER
# =========================================================

def _verify_target_visibility(
    image_path,
    target,
    context=""
):
    """
    Second-pass verifier.

    TIDAK memverifikasi crosshair.

    Tugasnya hanya menjawab:
    target yang diminta benar-benar terlihat atau tidak?

    Ini penting agar:
    - Save As yang masih tersembunyi ditolak.
    - File yang benar-benar terlihat tidak ditolak
      hanya karena model gagal memahami marker koordinat.
    """

    instruction = f"""
Kamu adalah verifier VISIBILITAS elemen UI desktop Windows.

TARGET:
{target}

KONTEKS:
{context}


=========================================================
TUGAS
=========================================================

Tentukan apakah TARGET benar-benar TERLIHAT
pada piksel gambar yang diberikan.


=========================================================
ATURAN
=========================================================

- Jangan mencari koordinat.

- Jangan menebak berdasarkan pengetahuan
  tentang struktur aplikasi.

- Nama target yang tertulis di prompt
  BUKAN bukti bahwa target terlihat.

- Nama target pada log, source code,
  Command Prompt, VS Code, ChatGPT,
  terminal, atau aplikasi lain yang tidak relevan
  BUKAN bukti.

- Jika target memiliki lebih dari satu kata,
  semua kata harus terlihat sebagai SATU
  label/control yang sama.

Contoh:

TARGET:
Save As

Tulisan "Save" saja BUKAN "Save As".

Tulisan "As" saja BUKAN "Save As".

Jika target mungkin berada di dalam sebuah menu
tetapi menu tersebut belum dibuka:

visible=false

Jika target benar-benar terbaca atau terlihat
sebagai control UI:

visible=true


matched_text:

Isi dengan tulisan target yang benar-benar terbaca
pada gambar.

Jika target icon tanpa teks,
matched_text boleh kosong.


Confidence:

0.0 = tidak yakin
1.0 = sangat yakin


Balas HANYA JSON:

{{
  "visible": false,
  "confidence": 0.0,
  "matched_text": "",
  "reason": ""
}}

Jangan gunakan markdown.
Jangan beri teks lain.
""".strip()

    print(
        "[SCREEN LOCATE] "
        f"Memastikan '{target}' "
        f"benar-benar terlihat..."
    )

    try:

        raw = analyze_image(
            image_path,
            instruction
        )

        data = _extract_json(
            raw
        )

    except Exception as error:

        print(
            "[SCREEN LOCATE] "
            "Verifier visibilitas gagal: "
            f"{error}"
        )

        return {
            "available": False,
            "verified": False,
            "confidence": 0.0,
            "matched_text": "",
            "reason": str(
                error
            )
        }

    visible = data.get(
        "visible",
        False
    )

    if not isinstance(
        visible,
        bool
    ):

        visible = False

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

    matched_text = str(
        data.get(
            "matched_text",
            ""
        )
        or ""
    ).strip()

    reason = str(
        data.get(
            "reason",
            ""
        )
        or ""
    ).strip()

    verified = (
        visible
        and
        confidence
        >=
        MIN_VISIBILITY_CONFIDENCE
    )

    if verified:

        print(
            "[SCREEN LOCATE] "
            "Target terlihat "
            f"(confidence="
            f"{confidence:.2f})."
        )

    else:

        print(
            "[SCREEN LOCATE] "
            "Target belum terverifikasi terlihat "
            f"(visible={visible}, "
            f"confidence={confidence:.2f})."
        )

    return {
        "available": True,
        "verified": verified,
        "raw_visible": visible,
        "confidence": confidence,
        "matched_text": matched_text,
        "reason": reason
    }


# =========================================================
# VISION LOCALIZATION
# =========================================================

def _locate_with_vision(
    image_path,
    target,
    width,
    height,
    context=""
):

    rejected_points = []

    last_confidence = 0.0
    last_description = ""
    last_validation = None

    for attempt in range(
        1,
        MAX_LOCALIZATION_ATTEMPTS + 1
    ):

        rejected_text = ""

        if rejected_points:

            rejected_lines = []

            for rejected in rejected_points:

                rejected_lines.append(
                    (
                        f"- ({rejected['x']}, "
                        f"{rejected['y']}): "
                        f"{rejected.get('reason', '')}"
                    )
                )

            rejected_text = (
                "\n\n"
                "KANDIDAT YANG SUDAH DITOLAK:\n"
                +
                "\n".join(
                    rejected_lines
                )
                +
                "\n"
                "Jangan gunakan kandidat itu lagi."
            )

        instruction = f"""
Kamu adalah visual localization system untuk desktop Windows.

Cari SATU elemen UI berikut pada gambar:

TARGET:
{target}

KONTEKS:
{context}

UKURAN GAMBAR:
width = {width}
height = {height}

{rejected_text}


=========================================================
ATURAN
=========================================================

Cari TARGET hanya berdasarkan piksel yang
benar-benar terlihat.

Jangan menebak target yang masih tersembunyi
di dalam menu, dropdown, submenu, panel,
atau halaman yang belum dibuka.

Nama target yang ada di prompt BUKAN bukti
bahwa target terlihat.


Target dapat berupa:

- teks menu
- item menu
- tombol
- tab
- icon
- checkbox
- dropdown
- submenu
- context menu
- popup
- flyout
- overlay
- kolom input
- link
- label UI


Jika target berupa teks:

- baca tulisan yang benar-benar terlihat
- cocokkan SELURUH label
- jangan hanya cocokkan salah satu kata

Contoh:

TARGET:
Save As

"Save" saja BUKAN "Save As".
"As" saja BUKAN "Save As".


matched_text:

Isi dengan tulisan UI yang benar-benar
terbaca pada target.

Untuk icon tanpa teks boleh kosong.


BOUNDING BOX:

Jika batas control terlihat,
isi:

left
top
right
bottom

dalam pixel gambar ini.

Bounding box harus mengelilingi
control target secara masuk akal.

Jika bounding box tidak yakin,
boleh null dan gunakan x/y.


KOORDINAT:

x/y adalah titik aman untuk diklik.

- kiri atas gambar = 0,0
- X bertambah ke kanan
- Y bertambah ke bawah
- koordinat harus pixel GAMBAR INI


JANGAN:

- membuat koordinat generik
- menyalin angka dari prompt
- memilih area kosong
- memilih title bar kecuali target memang title bar
- memilih editor dokumen jika target adalah menu/tombol
- memilih aplikasi lain
- mengklaim target ditemukan kalau kontrolnya
  tidak benar-benar terlihat


Jika target tidak terlihat:

found=false
x=null
y=null
left=null
top=null
right=null
bottom=null


Balas HANYA JSON:

{{
  "found": false,
  "target": "{target}",
  "matched_text": "",
  "left": null,
  "top": null,
  "right": null,
  "bottom": null,
  "x": null,
  "y": null,
  "confidence": 0.0,
  "description": ""
}}

Jangan gunakan markdown.
Jangan beri teks lain.
""".strip()

        print(
            "[SCREEN LOCATE] "
            f"Vision mencari '{target}' "
            f"(attempt {attempt}/"
            f"{MAX_LOCALIZATION_ATTEMPTS})..."
        )

        try:

            raw = analyze_image(
                image_path,
                instruction
            )

            print(
                "[SCREEN LOCATE] "
                "Vision selesai."
            )

            data = _extract_json(
                raw
            )

        except Exception as error:

            # Jangan lempar error vision format ke recovery.py.
            # Skill source tidak rusak hanya karena model
            # sekali menghasilkan JSON jelek.
            print(
                "[SCREEN LOCATE] "
                "Output localization tidak valid: "
                f"{error}"
            )

            if (
                attempt
                <
                MAX_LOCALIZATION_ATTEMPTS
            ):

                continue

            return {
                "found": False,
                "x": None,
                "y": None,
                "confidence": last_confidence,

                "description": (
                    last_description
                    or
                    "Vision tidak menghasilkan "
                    "localization yang valid."
                ),

                "point_validation": (
                    last_validation
                )
            }

        found = data.get(
            "found",
            False
        )

        if not isinstance(
            found,
            bool
        ):

            found = False

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

        description = str(
            data.get(
                "description",
                ""
            )
            or ""
        ).strip()

        last_confidence = (
            confidence
        )

        last_description = (
            description
        )

        # =================================================
        # TARGET NOT VISIBLE
        # =================================================

        if not found:

            return {
                "found": False,
                "x": None,
                "y": None,
                "confidence": confidence,
                "description": description,
                "point_validation": None
            }

        # =================================================
        # LOW CONFIDENCE
        # =================================================

        if confidence < MIN_CONFIDENCE:

            return {
                "found": False,
                "x": None,
                "y": None,
                "confidence": confidence,

                "description": (
                    description
                    +
                    " | confidence terlalu rendah"
                ),

                "point_validation": None
            }

        # =================================================
        # GET BBOX / COORDINATE
        # =================================================

        try:

            (
                x,
                y,
                bbox
            ) = _extract_candidate_coordinates(
                data,
                width,
                height
            )

        except Exception as error:

            print(
                "[SCREEN LOCATE] "
                "Kandidat koordinat ditolak: "
                f"{error}"
            )

            if (
                attempt
                <
                MAX_LOCALIZATION_ATTEMPTS
            ):

                continue

            return {
                "found": False,
                "x": None,
                "y": None,
                "confidence": confidence,
                "description": str(
                    error
                ),
                "point_validation": None
            }

        # =================================================
        # DESCRIPTION SANITY CHECK
        # =================================================

        if not _description_position_matches(
            description,
            x,
            y,
            width,
            height
        ):

            rejected_points.append({
                "x": x,
                "y": y,

                "reason": (
                    "Deskripsi posisi tidak cocok "
                    "dengan koordinat."
                )
            })

            print(
                "[SCREEN LOCATE] "
                "Kandidat ditolak karena deskripsi "
                "posisi tidak cocok."
            )

            if (
                attempt
                <
                MAX_LOCALIZATION_ATTEMPTS
            ):

                continue

            return {
                "found": False,
                "x": None,
                "y": None,
                "confidence": confidence,

                "description": (
                    "Kandidat vision ditolak karena "
                    "deskripsi posisi tidak cocok."
                ),

                "point_validation": None
            }

        print(
            "[SCREEN LOCATE] "
            f"Kandidat vision: "
            f"({x}, {y}), "
            f"confidence={confidence:.2f}"
        )

        # =================================================
        # SECOND PASS:
        # VERIFY TARGET EXISTS, NOT CROSSHAIR
        # =================================================

        visibility_validation = (
            _verify_target_visibility(
                image_path=image_path,
                target=target,
                context=context
            )
        )

        last_validation = (
            visibility_validation
        )

        if visibility_validation.get(
            "verified",
            False
        ):

            return {
                "found": True,

                "x": x,
                "y": y,

                "confidence": confidence,

                "description": (
                    description
                ),

                "matched_text": str(
                    data.get(
                        "matched_text",
                        ""
                    )
                    or ""
                ).strip(),

                "bbox": bbox,

                # Nama lama dipertahankan supaya caller
                # yang sudah membaca key ini tidak rusak.
                "point_validation": (
                    visibility_validation
                )
            }

        rejected_points.append({
            "x": x,
            "y": y,

            "reason": (
                visibility_validation.get(
                    "reason"
                )
                or
                "Target tidak terverifikasi "
                "terlihat pada gambar."
            )
        })

        if (
            attempt
            <
            MAX_LOCALIZATION_ATTEMPTS
        ):

            print(
                "[SCREEN LOCATE] "
                "Kandidat ditolak oleh verifier "
                "visibilitas. Mencari ulang sekali lagi..."
            )

            continue

        return {
            "found": False,
            "x": None,
            "y": None,

            "confidence": confidence,

            "description": (
                description
                +
                " | target tidak terverifikasi "
                "benar-benar terlihat"
            ),

            "point_validation": (
                visibility_validation
            )
        }

    return {
        "found": False,
        "x": None,
        "y": None,

        "confidence": (
            last_confidence
        ),

        "description": (
            last_description
        ),

        "point_validation": (
            last_validation
        )
    }


# =========================================================
# FRESH SCREENSHOT
# =========================================================

def _capture_fresh_screen():

    print(
        "[SCREEN LOCATE] "
        "Mengambil screenshot baru..."
    )

    result = screen_capture_run(
        mode="latest"
    )

    path = result.get(
        "path"
    )

    if not path:

        raise RuntimeError(
            "screen_capture tidak "
            "mengembalikan path."
        )

    if not os.path.isfile(
        path
    ):

        raise FileNotFoundError(
            f"Screenshot tidak ditemukan: "
            f"{path}"
        )

    return path


# =========================================================
# WINDOW CROP
# =========================================================

def _create_window_crop(
    image_path,
    window,
    screen_width,
    screen_height,
    crop_mode="full"
):

    with Image.open(
        image_path
    ) as image:

        image = image.convert(
            "RGB"
        )

        (
            image_width,
            image_height
        ) = image.size

        scale_x = (
            image_width
            /
            max(
                screen_width,
                1
            )
        )

        scale_y = (
            image_height
            /
            max(
                screen_height,
                1
            )
        )

        window_x = int(
            window.get(
                "x",
                0
            )
        )

        window_y = int(
            window.get(
                "y",
                0
            )
        )

        window_width = int(
            window.get(
                "width",
                0
            )
        )

        window_height = int(
            window.get(
                "height",
                0
            )
        )

        if (
            window_width <= 0
            or
            window_height <= 0
        ):

            raise ValueError(
                "Ukuran window tidak valid."
            )

        crop_left_screen = (
            window_x
        )

        crop_top_screen = (
            window_y
        )

        crop_right_screen = (
            window_x
            +
            window_width
        )

        crop_bottom_screen = (
            window_y
            +
            window_height
        )

        # =================================================
        # TITLEBAR
        # =================================================

        if crop_mode == "titlebar":

            crop_bottom_screen = (
                window_y
                +
                min(
                    110,
                    window_height
                )
            )

        # =================================================
        # TOP UI
        # =================================================

        elif crop_mode == "top_ui":

            crop_bottom_screen = (
                window_y
                +
                min(
                    220,
                    window_height
                )
            )

        # =================================================
        # POPUP / DROPDOWN AREA
        # =================================================

        elif crop_mode == "expanded":

            crop_left_screen = (
                window_x
                -
                260
            )

            crop_top_screen = (
                window_y
                -
                100
            )

            crop_right_screen = (
                window_x
                +
                window_width
                +
                360
            )

            crop_bottom_screen = (
                window_y
                +
                window_height
                +
                420
            )

        # =================================================
        # CLAMP SCREEN
        # =================================================

        crop_left_screen = max(
            0,
            crop_left_screen
        )

        crop_top_screen = max(
            0,
            crop_top_screen
        )

        crop_right_screen = min(
            screen_width,
            crop_right_screen
        )

        crop_bottom_screen = min(
            screen_height,
            crop_bottom_screen
        )

        # =================================================
        # SCREEN -> IMAGE
        # =================================================

        left = round(
            crop_left_screen
            *
            scale_x
        )

        top = round(
            crop_top_screen
            *
            scale_y
        )

        right = round(
            crop_right_screen
            *
            scale_x
        )

        bottom = round(
            crop_bottom_screen
            *
            scale_y
        )

        left = max(
            0,
            min(
                left,
                image_width - 1
            )
        )

        top = max(
            0,
            min(
                top,
                image_height - 1
            )
        )

        right = max(
            left + 1,
            min(
                right,
                image_width
            )
        )

        bottom = max(
            top + 1,
            min(
                bottom,
                image_height
            )
        )

        source_crop = image.crop(
            (
                left,
                top,
                right,
                bottom
            )
        )

        (
            source_width,
            source_height
        ) = source_crop.size

        # =================================================
        # UPSCALE SMALL UI
        # =================================================

        vision_scale = 1.0

        if (
            source_width < 1000
            or
            source_height < 650
        ):

            vision_scale = 2.0

        max_width = 1800
        max_height = 1400

        vision_scale = min(
            vision_scale,

            max_width
            /
            max(
                source_width,
                1
            ),

            max_height
            /
            max(
                source_height,
                1
            )
        )

        vision_scale = max(
            1.0,
            vision_scale
        )

        if vision_scale > 1.05:

            vision_width = round(
                source_width
                *
                vision_scale
            )

            vision_height = round(
                source_height
                *
                vision_scale
            )

            resampling = getattr(
                Image,
                "Resampling",
                Image
            ).LANCZOS

            vision_crop = (
                source_crop.resize(
                    (
                        vision_width,
                        vision_height
                    ),
                    resampling
                )
            )

        else:

            vision_crop = (
                source_crop
            )

            vision_width = (
                source_width
            )

            vision_height = (
                source_height
            )

        vision_crop.save(
            CROP_PATH
        )

    return {
        "path": (
            CROP_PATH
        ),

        "width": (
            vision_width
        ),

        "height": (
            vision_height
        ),

        "source_width": (
            source_width
        ),

        "source_height": (
            source_height
        ),

        "vision_scale_x": (
            vision_width
            /
            max(
                source_width,
                1
            )
        ),

        "vision_scale_y": (
            vision_height
            /
            max(
                source_height,
                1
            )
        ),

        "image_left": (
            left
        ),

        "image_top": (
            top
        ),

        "screen_image_scale_x": (
            scale_x
        ),

        "screen_image_scale_y": (
            scale_y
        ),

        "crop_mode": (
            crop_mode
        )
    }


# =========================================================
# MATCH WINDOW CONTEXT
# =========================================================

def _resolve_window_context(
    original_target,
    element_target,
    window_hint,
    windows,
    state
):

    # =====================================================
    # EXPLICIT WINDOW
    # =====================================================

    if window_hint:

        matched_window, score = (
            _find_best_window(
                window_hint,
                windows
            )
        )

        if matched_window is not None:

            return (
                matched_window,
                score,
                "explicit_window_hint"
            )

        return (
            None,
            score,
            "explicit_window_hint_failed"
        )

    # =====================================================
    # WHOLE WINDOW
    # =====================================================

    if _is_whole_window_target(
        original_target
    ):

        matched_window, score = (
            _find_best_window(
                original_target,
                windows
            )
        )

        return (
            matched_window,
            score,
            "window_title_match"
        )

    active_window = (
        _active_window_from_state(
            state
        )
    )

    # =====================================================
    # GENERIC UI
    # =====================================================

    if (
        active_window is not None
        and
        (
            _target_has_ui_hint(
                element_target
            )
            or
            _is_generic_ui_label(
                element_target
            )
        )
    ):

        return (
            active_window,
            0.85,
            "active_window_ui_context"
        )

    # =====================================================
    # WINDOW TITLE MATCH
    # =====================================================

    matched_window, score = (
        _find_best_window(
            original_target,
            windows
        )
    )

    if matched_window is not None:

        return (
            matched_window,
            score,
            "window_title_match"
        )

    # =====================================================
    # ACTIVE FALLBACK
    # =====================================================

    if (
        active_window is not None
        and
        (
            _target_has_ui_hint(
                element_target
            )
            or
            _is_generic_ui_label(
                element_target
            )
        )
    ):

        return (
            active_window,
            0.70,
            "active_window_fallback"
        )

    return (
        None,
        score,
        "no_window_context"
    )


# =========================================================
# VISION INSIDE / AROUND WINDOW
# =========================================================

def _locate_inside_window(
    image_path,
    matched_window,
    original_target,
    element_target,
    window_hint,
    screen_width,
    screen_height,
    allow_popup=True
):

    preferred_mode = (
        _crop_mode_for_target(
            element_target
        )
    )

    crop_modes = [
        preferred_mode
    ]

    if "full" not in crop_modes:

        crop_modes.append(
            "full"
        )

    if (
        allow_popup
        and
        "expanded" not in crop_modes
    ):

        crop_modes.append(
            "expanded"
        )

    last_result = None
    last_crop = None

    attempted_modes = []

    for crop_mode in crop_modes:

        attempted_modes.append(
            crop_mode
        )

        if crop_mode == "top_ui":

            print(
                "[SCREEN LOCATE] "
                "Target UI area atas terdeteksi → "
                "crop difokuskan ke bagian atas window."
            )

        elif crop_mode == "titlebar":

            print(
                "[SCREEN LOCATE] "
                "Target title bar terdeteksi → "
                "crop dipersempit."
            )

        elif (
            crop_mode == "full"
            and
            preferred_mode != "full"
        ):

            print(
                "[SCREEN LOCATE] "
                "Crop khusus belum menemukan target → "
                "fallback ke full window."
            )

        elif crop_mode == "expanded":

            print(
                "[SCREEN LOCATE] "
                "Mencari popup/dropdown/submenu "
                "di sekitar window..."
            )

        crop_info = (
            _create_window_crop(
                image_path,
                matched_window,
                screen_width,
                screen_height,
                crop_mode=crop_mode
            )
        )

        if crop_mode == "expanded":

            context_lines = [
                (
                    "Target berhubungan dengan window berikut:"
                ),

                str(
                    matched_window.get(
                        "title",
                        ""
                    )
                ),

                (
                    "Gambar mencakup window tersebut DAN "
                    "area di sekelilingnya."
                ),

                (
                    "Target boleh berada di popup, dropdown, "
                    "context menu, submenu, flyout, atau overlay "
                    "yang berasal dari window tersebut."
                ),

                (
                    "Jangan memilih elemen aplikasi lain "
                    "yang kebetulan berada di area gambar."
                )
            ]

        else:

            context_lines = [
                (
                    "Target dicari DI DALAM window berikut:"
                ),

                str(
                    matched_window.get(
                        "title",
                        ""
                    )
                ),

                (
                    "Gambar sudah di-crop "
                    "ke area window tersebut."
                ),

                (
                    "Cari elemen target, bukan nama window."
                )
            ]

            if allow_popup:

                context_lines.append(
                    (
                        "Popup/dropdown/submenu mungkin sudah "
                        "terbuka karena kontrol sebelumnya "
                        "baru saja diklik."
                    )
                )

        if window_hint:

            context_lines.append(
                (
                    "Nama window yang diminta user: "
                    +
                    window_hint
                )
            )

        context_lines.append(
            (
                "Permintaan asli user untuk locator: "
                +
                original_target
            )
        )

        context = "\n".join(
            context_lines
        )

        local_result = (
            _locate_with_vision(
                crop_info[
                    "path"
                ],

                element_target,

                crop_info[
                    "width"
                ],

                crop_info[
                    "height"
                ],

                context=context
            )
        )

        last_result = (
            local_result
        )

        last_crop = (
            crop_info
        )

        if local_result[
            "found"
        ]:

            # =============================================
            # VISION -> SOURCE CROP
            # =============================================

            source_local_x = (
                local_result[
                    "x"
                ]
                /
                crop_info[
                    "vision_scale_x"
                ]
            )

            source_local_y = (
                local_result[
                    "y"
                ]
                /
                crop_info[
                    "vision_scale_y"
                ]
            )

            # =============================================
            # SOURCE CROP -> SCREENSHOT
            # =============================================

            absolute_image_x = (
                crop_info[
                    "image_left"
                ]
                +
                source_local_x
            )

            absolute_image_y = (
                crop_info[
                    "image_top"
                ]
                +
                source_local_y
            )

            # =============================================
            # SCREENSHOT -> DESKTOP
            # =============================================

            desktop_x = round(
                absolute_image_x
                /
                crop_info[
                    "screen_image_scale_x"
                ]
            )

            desktop_y = round(
                absolute_image_y
                /
                crop_info[
                    "screen_image_scale_y"
                ]
            )

            desktop_x = max(
                0,
                min(
                    desktop_x,
                    screen_width - 1
                )
            )

            desktop_y = max(
                0,
                min(
                    desktop_y,
                    screen_height - 1
                )
            )

            return {
                "found": True,

                "x": (
                    desktop_x
                ),

                "y": (
                    desktop_y
                ),

                "confidence": (
                    local_result[
                        "confidence"
                    ]
                ),

                "description": (
                    local_result[
                        "description"
                    ]
                ),

                "matched_text": (
                    local_result.get(
                        "matched_text"
                    )
                ),

                "bbox": (
                    local_result.get(
                        "bbox"
                    )
                ),

                "local_x": (
                    local_result[
                        "x"
                    ]
                ),

                "local_y": (
                    local_result[
                        "y"
                    ]
                ),

                # Nama key lama dipertahankan
                # agar ui_click lama tetap kompatibel.
                "point_validation": (
                    local_result.get(
                        "point_validation"
                    )
                ),

                "crop_info": (
                    crop_info
                ),

                "attempted_crop_modes": (
                    attempted_modes
                )
            }

    return {
        "found": False,

        "x": None,
        "y": None,

        "confidence": (
            last_result.get(
                "confidence",
                0.0
            )
            if isinstance(
                last_result,
                dict
            )
            else 0.0
        ),

        "description": (
            last_result.get(
                "description",
                ""
            )
            if isinstance(
                last_result,
                dict
            )
            else ""
        ),

        "local_x": None,
        "local_y": None,

        "point_validation": (
            last_result.get(
                "point_validation"
            )
            if isinstance(
                last_result,
                dict
            )
            else None
        ),

        "crop_info": (
            last_crop
        ),

        "attempted_crop_modes": (
            attempted_modes
        )
    }


# =========================================================
# MAIN
# =========================================================

def run(
    target=None,

    # Alias semantik agar caller yang memakai
    # screen_locate(text="Save As") tidak crash.
    text=None,
    query=None,

    window_hint=None,
    window_title=None,
    title=None,

    verify=None,

    allow_popup=True
):
    """
    Mencari target UI.

    target:
        parameter utama.

    text / query:
        alias untuk target.

    window_hint / window_title / title:
        alias konteks window.

    verify:
        hanya diterima untuk kompatibilitas caller.

    screen_locate TIDAK melakukan klik.
    """

    # =====================================================
    # TARGET ALIAS
    # =====================================================

    if not target:

        target = (
            text
            or
            query
            or
            None
        )

    # =====================================================
    # WINDOW ALIAS
    # =====================================================

    supplied_window_hint = (
        window_hint
        or
        window_title
        or
        None
    )

    if (
        not target
        and
        title
    ):

        target = (
            f"jendela {title}"
        )

    elif (
        target
        and
        title
        and
        not supplied_window_hint
    ):

        supplied_window_hint = (
            title
        )

    target = str(
        target or ""
    ).strip()

    if not target:

        raise ValueError(
            "Target visual belum diberikan."
        )

    allow_popup = bool(
        allow_popup
    )

    # =====================================================
    # PARSE TARGET + WINDOW
    # =====================================================

    parsed = (
        _parse_target_context(
            target
        )
    )

    element_target = (
        parsed[
            "element_target"
        ]
    )

    parsed_window_hint = (
        parsed[
            "window_hint"
        ]
    )

    if supplied_window_hint:

        final_window_hint = (
            _clean_window_hint(
                supplied_window_hint
            )
        )

    else:

        final_window_hint = (
            parsed_window_hint
        )

    if final_window_hint:

        print(
            "[SCREEN LOCATE] "
            f"Konteks target dipisahkan → "
            f"elemen='{element_target}', "
            f"window='{final_window_hint}'."
        )

    # =====================================================
    # SCREENSHOT
    # =====================================================

    image_path = (
        _capture_fresh_screen()
    )

    with Image.open(
        image_path
    ) as screenshot:

        (
            image_width,
            image_height
        ) = screenshot.size

    # =====================================================
    # WINDOWS METADATA
    # =====================================================

    state = screen_state_run(
        include_windows=True,
        max_windows=50
    )

    screen = state.get(
        "screen",
        {}
    )

    screen_width = int(
        screen.get(
            "width",
            image_width
        )
    )

    screen_height = int(
        screen.get(
            "height",
            image_height
        )
    )

    windows = state.get(
        "windows",
        []
    )

    # =====================================================
    # RESOLVE WINDOW
    # =====================================================

    (
        matched_window,
        match_score,
        context_source
    ) = _resolve_window_context(
        original_target=target,
        element_target=element_target,
        window_hint=final_window_hint,
        windows=windows,
        state=state
    )

    if matched_window is not None:

        print(
            "[SCREEN LOCATE] "
            f"Window terpilih: "
            f"{matched_window.get('title')} "
            f"(score={match_score:.3f}, "
            f"source={context_source})"
        )

    # =====================================================
    # WHOLE WINDOW
    # =====================================================

    if (
        matched_window is not None
        and
        _is_whole_window_target(
            target
        )
    ):

        window_x = int(
            matched_window.get(
                "x",
                0
            )
        )

        window_y = int(
            matched_window.get(
                "y",
                0
            )
        )

        window_width = int(
            matched_window.get(
                "width",
                0
            )
        )

        window_height = int(
            matched_window.get(
                "height",
                0
            )
        )

        center_x = round(
            window_x
            +
            (
                window_width
                / 2
            )
        )

        center_y = round(
            window_y
            +
            (
                window_height
                / 2
            )
        )

        print(
            "[SCREEN LOCATE] "
            "Window ditemukan lewat metadata Windows."
        )

        return {
            "message": (
                f"Target window '{target}' "
                f"ditemukan secara presisi "
                f"di sekitar "
                f"({center_x}, {center_y})."
            ),

            "found": True,

            "target": (
                target
            ),

            "element_target": (
                element_target
            ),

            "window_hint": (
                final_window_hint
            ),

            "x": (
                center_x
            ),

            "y": (
                center_y
            ),

            "confidence": 1.0,

            "description": (
                "Posisi diperoleh dari metadata "
                "window Windows, bukan tebakan vision."
            ),

            "source": (
                "window_metadata"
            ),

            "window_context_source": (
                context_source
            ),

            "matched_window": (
                matched_window
            ),

            "window_match_score": (
                round(
                    match_score,
                    3
                )
            ),

            "path": (
                image_path
            ),

            "screen_width": (
                screen_width
            ),

            "screen_height": (
                screen_height
            )
        }

    # =====================================================
    # STANDARD WINDOWS CONTROL
    # =====================================================

    standard_control = (
        _detect_standard_window_control(
            element_target
        )
    )

    if (
        matched_window is not None
        and
        standard_control is not None
    ):

        print(
            "[SCREEN LOCATE] "
            f"Kontrol standar Windows "
            f"terdeteksi: {standard_control}"
        )

        control_result = (
            _locate_standard_window_control(
                matched_window,
                standard_control,
                screen_width,
                screen_height
            )
        )

        if control_result:

            print(
                "[SCREEN LOCATE] "
                f"Posisi {standard_control} "
                f"diperoleh tanpa vision."
            )

            return {
                "message": (
                    f"Target '{target}' ditemukan "
                    f"di sekitar koordinat desktop "
                    f"({control_result['x']}, "
                    f"{control_result['y']})."
                ),

                "found": True,

                "target": (
                    target
                ),

                "element_target": (
                    element_target
                ),

                "window_hint": (
                    final_window_hint
                ),

                "x": (
                    control_result[
                        "x"
                    ]
                ),

                "y": (
                    control_result[
                        "y"
                    ]
                ),

                "confidence": (
                    control_result[
                        "confidence"
                    ]
                ),

                "description": (
                    f"Tombol {standard_control} "
                    f"pada title bar window "
                    f"'{matched_window.get('title')}'. "
                    f"Posisi diperoleh dari Windows."
                ),

                "source": (
                    control_result[
                        "source"
                    ]
                ),

                "control": (
                    standard_control
                ),

                "control_rect": (
                    control_result[
                        "control_rect"
                    ]
                ),

                "window_context_source": (
                    context_source
                ),

                "matched_window": (
                    matched_window
                ),

                "window_match_score": (
                    round(
                        match_score,
                        3
                    )
                ),

                "path": (
                    image_path
                ),

                "screen_width": (
                    screen_width
                ),

                "screen_height": (
                    screen_height
                )
            }

    # =====================================================
    # ELEMENT INSIDE / AROUND WINDOW
    # =====================================================

    if matched_window is not None:

        print(
            "[SCREEN LOCATE] "
            f"Window konteks ditemukan: "
            f"{matched_window.get('title')}"
        )

        print(
            "[SCREEN LOCATE] "
            f"Vision hanya akan mencari elemen: "
            f"'{element_target}'"
        )

        local_result = (
            _locate_inside_window(
                image_path=image_path,

                matched_window=(
                    matched_window
                ),

                original_target=(
                    target
                ),

                element_target=(
                    element_target
                ),

                window_hint=(
                    final_window_hint
                ),

                screen_width=(
                    screen_width
                ),

                screen_height=(
                    screen_height
                ),

                allow_popup=(
                    allow_popup
                )
            )
        )

        crop_info = (
            local_result.get(
                "crop_info"
            )
            or {}
        )

        if not local_result[
            "found"
        ]:

            return {
                "message": (
                    f"Target '{element_target}' "
                    f"tidak ditemukan dengan yakin "
                    f"di atau sekitar window "
                    f"'{matched_window.get('title')}'."
                ),

                "found": False,

                "target": (
                    target
                ),

                "element_target": (
                    element_target
                ),

                "window_hint": (
                    final_window_hint
                ),

                "x": None,
                "y": None,

                "confidence": (
                    local_result[
                        "confidence"
                    ]
                ),

                "description": (
                    local_result[
                        "description"
                    ]
                ),

                "source": (
                    "window_crop_vision"
                ),

                "window_context_source": (
                    context_source
                ),

                "matched_window": (
                    matched_window
                ),

                "window_match_score": (
                    round(
                        match_score,
                        3
                    )
                ),

                "attempted_crop_modes": (
                    local_result[
                        "attempted_crop_modes"
                    ]
                ),

                "candidate_validation": (
                    local_result.get(
                        "point_validation"
                    )
                ),

                "crop_mode": (
                    crop_info.get(
                        "crop_mode"
                    )
                ),

                "crop_path": (
                    crop_info.get(
                        "path"
                    )
                ),

                "path": (
                    image_path
                ),

                "screen_width": (
                    screen_width
                ),

                "screen_height": (
                    screen_height
                )
            }

        return {
            "message": (
                f"Target '{element_target}' ditemukan "
                f"dan terverifikasi terlihat "
                f"di sekitar koordinat desktop "
                f"({local_result['x']}, "
                f"{local_result['y']})."
            ),

            "found": True,

            "target": (
                target
            ),

            "element_target": (
                element_target
            ),

            "window_hint": (
                final_window_hint
            ),

            "x": (
                local_result[
                    "x"
                ]
            ),

            "y": (
                local_result[
                    "y"
                ]
            ),

            "confidence": (
                local_result[
                    "confidence"
                ]
            ),

            "description": (
                local_result[
                    "description"
                ]
            ),

            "matched_text": (
                local_result.get(
                    "matched_text"
                )
            ),

            "bbox": (
                local_result.get(
                    "bbox"
                )
            ),

            "source": (
                "window_crop_vision"
            ),

            "window_context_source": (
                context_source
            ),

            "matched_window": (
                matched_window
            ),

            "window_match_score": (
                round(
                    match_score,
                    3
                )
            ),

            "local_x": (
                local_result[
                    "local_x"
                ]
            ),

            "local_y": (
                local_result[
                    "local_y"
                ]
            ),

            "candidate_validation": (
                local_result.get(
                    "point_validation"
                )
            ),

            "crop_width": (
                crop_info.get(
                    "width"
                )
            ),

            "crop_height": (
                crop_info.get(
                    "height"
                )
            ),

            "crop_mode": (
                crop_info.get(
                    "crop_mode"
                )
            ),

            "vision_scale_x": (
                crop_info.get(
                    "vision_scale_x"
                )
            ),

            "vision_scale_y": (
                crop_info.get(
                    "vision_scale_y"
                )
            ),

            "attempted_crop_modes": (
                local_result[
                    "attempted_crop_modes"
                ]
            ),

            "crop_path": (
                crop_info.get(
                    "path"
                )
            ),

            "path": (
                image_path
            ),

            "screen_width": (
                screen_width
            ),

            "screen_height": (
                screen_height
            )
        }

    # =====================================================
    # EXPLICIT WINDOW NOT FOUND
    # =====================================================

    if final_window_hint:

        return {
            "message": (
                f"Window konteks '{final_window_hint}' "
                f"tidak ditemukan. "
                f"Target '{element_target}' tidak dicari "
                f"di window lain agar tidak salah klik."
            ),

            "found": False,

            "target": (
                target
            ),

            "element_target": (
                element_target
            ),

            "window_hint": (
                final_window_hint
            ),

            "x": None,
            "y": None,

            "confidence": 0.0,

            "description": (
                "Window yang secara eksplisit disebut user "
                "tidak ditemukan."
            ),

            "source": (
                "explicit_window_not_found"
            ),

            "window_context_source": (
                context_source
            ),

            "path": (
                image_path
            ),

            "screen_width": (
                screen_width
            ),

            "screen_height": (
                screen_height
            )
        }

    # =====================================================
    # FULL SCREEN FALLBACK
    # =====================================================

    print(
        "[SCREEN LOCATE] "
        "Window konteks tidak ditemukan. "
        "Fallback ke full-screen vision."
    )

    full_result = (
        _locate_with_vision(
            image_path,
            element_target,
            image_width,
            image_height,

            context=(
                "Tidak ada window spesifik yang "
                "berhasil dicocokkan dari metadata Windows. "
                "Cari target pada seluruh screenshot."
            )
        )
    )

    if not full_result[
        "found"
    ]:

        return {
            "message": (
                f"Target '{element_target}' "
                f"tidak ditemukan dengan yakin."
            ),

            "found": False,

            "target": (
                target
            ),

            "element_target": (
                element_target
            ),

            "window_hint": None,

            "x": None,
            "y": None,

            "confidence": (
                full_result[
                    "confidence"
                ]
            ),

            "description": (
                full_result[
                    "description"
                ]
            ),

            "candidate_validation": (
                full_result.get(
                    "point_validation"
                )
            ),

            "source": (
                "full_screen_vision"
            ),

            "path": (
                image_path
            ),

            "screen_width": (
                screen_width
            ),

            "screen_height": (
                screen_height
            )
        }

    screenshot_scale_x = (
        image_width
        /
        max(
            screen_width,
            1
        )
    )

    screenshot_scale_y = (
        image_height
        /
        max(
            screen_height,
            1
        )
    )

    desktop_x = round(
        full_result[
            "x"
        ]
        /
        screenshot_scale_x
    )

    desktop_y = round(
        full_result[
            "y"
        ]
        /
        screenshot_scale_y
    )

    desktop_x = max(
        0,
        min(
            desktop_x,
            screen_width - 1
        )
    )

    desktop_y = max(
        0,
        min(
            desktop_y,
            screen_height - 1
        )
    )

    return {
        "message": (
            f"Target '{element_target}' ditemukan "
            f"dan terverifikasi terlihat "
            f"di sekitar "
            f"({desktop_x}, {desktop_y})."
        ),

        "found": True,

        "target": (
            target
        ),

        "element_target": (
            element_target
        ),

        "window_hint": None,

        "x": (
            desktop_x
        ),

        "y": (
            desktop_y
        ),

        "confidence": (
            full_result[
                "confidence"
            ]
        ),

        "description": (
            full_result[
                "description"
            ]
        ),

        "matched_text": (
            full_result.get(
                "matched_text"
            )
        ),

        "bbox": (
            full_result.get(
                "bbox"
            )
        ),

        "candidate_validation": (
            full_result.get(
                "point_validation"
            )
        ),

        "source": (
            "full_screen_vision"
        ),

        "path": (
            image_path
        ),

        "screen_width": (
            screen_width
        ),

        "screen_height": (
            screen_height
        )
    }


# =========================================================
# TOOL
# =========================================================

TOOL = {
    "name": "screen_locate",

    "description": (
        "Mencari posisi target pada desktop Windows. "
        "Tool dapat memisahkan elemen UI dan konteks aplikasi, "
        "misalnya 'menu File di Notepad' menjadi elemen "
        "'menu File' di window 'Notepad'. "
        "Untuk target berbasis vision, locator menggunakan "
        "bounding box jika tersedia lalu melakukan second-pass "
        "verification yang hanya memastikan target benar-benar "
        "terlihat pada gambar. "
        "Verifier tidak lagi memakai crosshair koordinat, "
        "sehingga target valid seperti menu File tidak ditolak "
        "hanya karena verifier titik gagal membaca marker. "
        "Target yang belum terlihat seperti item di dalam menu "
        "tertutup tetap ditolak agar ui_click dapat melakukan "
        "navigasi UI terlebih dahulu. "
        "Mendukung popup, dropdown, submenu, context menu, "
        "flyout, dan overlay di sekitar window. "
        "Untuk Close, Minimize, dan Maximize standar Windows, "
        "posisi dicari secara deterministik melalui informasi "
        "title bar Windows jika memungkinkan. "
        "Alias target, text, dan query didukung. "
        "Tool ini hanya mencari posisi dan TIDAK melakukan klik."
    ),

    "parameters": {
        "target": {
            "type": "string",

            "description": (
                "Target yang ingin dicari. "
                "Contoh: 'menu File di Notepad', "
                "'Save As di Notepad', "
                "'kolom pencarian di ChatGPT', "
                "atau 'tombol Close X pada jendela Notepad'."
            )
        },

        "text": {
            "type": "string",

            "description": (
                "Alias untuk target."
            )
        },

        "query": {
            "type": "string",

            "description": (
                "Alias untuk target."
            )
        },

        "window_hint": {
            "type": "string",

            "description": (
                "Opsional nama window atau aplikasi "
                "yang menjadi konteks target."
            )
        },

        "window_title": {
            "type": "string",

            "description": (
                "Alias untuk window_hint."
            )
        },

        "title": {
            "type": "string",

            "description": (
                "Alias nama window. "
                "Jika target kosong, tool akan mencari "
                "whole window dengan nama ini."
            )
        },

        "verify": {
            "type": "boolean",

            "description": (
                "Diterima untuk kompatibilitas caller. "
                "screen_locate tetap tidak melakukan klik."
            )
        },

        "allow_popup": {
            "type": "boolean",

            "description": (
                "Jika true, setelah pencarian di dalam window "
                "gagal, locator juga mencari popup, dropdown, "
                "submenu, flyout, dan overlay di sekitar window. "
                "Default true."
            )
        }
    },

    "run": run
}