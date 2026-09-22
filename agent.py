import json
import time
import re

from difflib import SequenceMatcher

from tool_registry import registry
from recovery import attempt_recovery
from llm_runtime import agent_json


# =========================================================
# CONFIG
# =========================================================

ACTION_DELAY = 0.7

MAX_AGENT_STEPS = 8

MAX_ACTIONS_PER_STEP = 4

MAX_HISTORY_MESSAGES = 20

FUZZY_VERB_THRESHOLD = 0.74


# =========================================================
# OBSERVATION TOOLS
# =========================================================

OBSERVATION_TOOLS = {
    "screen_state",
    "screen_capture",
    "screen_vision",
    "screen_locate"
}


# =========================================================
# COMMAND VERBS
# =========================================================

OPEN_VERBS = (
    "buka",
    "buke",
    "bukain",
    "bukakan",
    "open"
)

CLOSE_VERBS = (
    "tutup",
    "tutupin",
    "tutupkan",
    "close"
)

CLICK_VERBS = (
    "klik",
    "click",
    "tekan",
    "pencet"
)

TYPE_VERBS = (
    "ketik",
    "tulis",
    "type",
    "write"
)

MOVE_VERBS = (
    "gerakkan",
    "gerakin",
    "geser",
    "pindahkan",
    "pindahin",
    "move"
)

CREATE_VERBS = (
    "buat",
    "bikin",
    "create"
)

REPAIR_VERBS = (
    "perbaiki",
    "betulkan",
    "repair"
)


# =========================================================
# ACTION DETECTION
# =========================================================

ACTION_HINTS = (
    "gerakkan",
    "gerakin",
    "bergerak",
    "pindahkan",
    "pindahin",
    "geser",

    "buka",
    "buke",
    "bukain",
    "bukakan",

    "tutup",

    "ketik",
    "tulis",
    "klik",
    "tekan",
    "jalankan",
    "jalanin",
    "buat",
    "bikin",
    "perbaiki",
    "fokuskan",
    "scroll",
    "seret",
    "drag",

    "move ",
    "open ",
    "close ",
    "type ",
    "write ",
    "click ",
    "press ",
    "run ",
    "create ",
    "repair "
)


# =========================================================
# MOUSE SEMANTIC HINTS
# =========================================================

RELATIVE_MOUSE_HINTS = (
    "ke kanan",
    "ke kiri",
    "ke atas",
    "ke bawah",
    "pixel ke kanan",
    "pixel ke kiri",
    "pixel ke atas",
    "pixel ke bawah",
    "px ke kanan",
    "px ke kiri",
    "px ke atas",
    "px ke bawah",
    "geser",
    "bergeser",
    "sejauh",
    "sedikit ke kanan",
    "sedikit ke kiri",
    "sedikit ke atas",
    "sedikit ke bawah"
)


ABSOLUTE_MOUSE_HINTS = (
    "ke koordinat",
    "koordinat x",
    "koordinat y",
    "posisi x",
    "posisi y",
    "ke posisi",
    "x=",
    "y=",
    "x =",
    "y ="
)


# =========================================================
# SEQUENCE CONNECTORS
# =========================================================

SEQUENCE_CONNECTORS = (
    " terus ",
    " lalu ",
    " kemudian ",
    " setelah itu ",
    " habis itu ",
    " abis itu "
)


# =========================================================
# TEXT HELPERS
# =========================================================

def _remove_pochi_prefix(text):

    text = str(
        text or ""
    ).strip()

    text = re.sub(
        r"^\s*pochi\s*[,:\-]?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    return text.strip()


def _remove_polite_prefix(text):

    text = str(
        text or ""
    ).strip()

    polite_prefixes = (
        "tolong ",
        "coba ",
        "please ",
        "mohon "
    )

    changed = True

    while changed:

        changed = False

        lowered = text.lower()

        for prefix in polite_prefixes:

            if lowered.startswith(
                prefix
            ):

                text = text[
                    len(prefix):
                ].strip()

                changed = True
                break

    return text


def _prepare_command_text(text):

    text = _remove_pochi_prefix(
        text
    )

    text = _remove_polite_prefix(
        text
    )

    return text.strip()


def _clean_end_punctuation(text):

    return str(
        text or ""
    ).strip(
        " \t\r\n.,!?;:\"'"
    )


def _normalize_word(word):

    return re.sub(
        r"[^a-z0-9]",
        "",
        str(
            word or ""
        ).lower()
    )


def _split_first_word(text):

    text = str(
        text or ""
    ).strip()

    if not text:

        return (
            "",
            ""
        )

    match = re.match(
        r"^([^\s,.:;!?]+)\s*(.*)$",
        text
    )

    if not match:

        return (
            "",
            text
        )

    first = _normalize_word(
        match.group(1)
    )

    rest = str(
        match.group(2)
        or ""
    ).strip()

    return (
        first,
        rest
    )


def _has_sequence_connector(text):

    padded = (
        " "
        + str(
            text or ""
        ).lower().strip()
        + " "
    )

    return any(
        connector in padded
        for connector in SEQUENCE_CONNECTORS
    )


# =========================================================
# FUZZY VERB MATCH
# =========================================================

def _match_verb(
    word,
    candidates,
    threshold=FUZZY_VERB_THRESHOLD
):
    """
    Mencocokkan kata kerja dengan toleransi typo ringan.

    Contoh:

    tutuo -> tutup
    tutp  -> tutup
    bukaa -> buka

    Tidak menggunakan daftar typo satu per satu.
    """

    word = _normalize_word(
        word
    )

    if not word:

        return {
            "matched": False,
            "candidate": None,
            "score": 0.0
        }

    normalized_candidates = [
        _normalize_word(
            item
        )
        for item in candidates
    ]

    # =====================================================
    # EXACT
    # =====================================================

    if word in normalized_candidates:

        return {
            "matched": True,
            "candidate": word,
            "score": 1.0
        }

    # Kata sangat pendek terlalu mudah false-positive.
    if len(word) < 3:

        return {
            "matched": False,
            "candidate": None,
            "score": 0.0
        }

    best_candidate = None
    best_score = 0.0

    for candidate in normalized_candidates:

        if not candidate:
            continue

        score = SequenceMatcher(
            None,
            word,
            candidate
        ).ratio()

        if score > best_score:

            best_score = score
            best_candidate = candidate

    return {
        "matched": (
            best_score >= threshold
        ),

        "candidate": (
            best_candidate
            if best_score >= threshold
            else None
        ),

        "score": best_score
    }


# =========================================================
# REQUEST TYPE
# =========================================================

def is_action_request(user_text):

    text = str(
        user_text or ""
    ).lower()

    # =====================================================
    # NORMAL EXACT CHECK
    # =====================================================

    if any(
        hint in text
        for hint in ACTION_HINTS
    ):
        return True

    # =====================================================
    # FUZZY FIRST VERB
    # =====================================================

    command_text = _prepare_command_text(
        user_text
    )

    first_word, _ = _split_first_word(
        command_text
    )

    action_verbs = (
        OPEN_VERBS
        + CLOSE_VERBS
        + CLICK_VERBS
        + TYPE_VERBS
        + MOVE_VERBS
        + CREATE_VERBS
        + REPAIR_VERBS
    )

    match = _match_verb(
        first_word,
        action_verbs
    )

    return bool(
        match[
            "matched"
        ]
    )


# =========================================================
# VISUAL REQUEST DETECTION
# =========================================================

def is_visual_request(user_text):
    """
    True jika user meminta Pochi benar-benar
    MELIHAT isi visual layar.
    """

    text = str(
        user_text or ""
    ).lower()

    direct_phrases = (
        "lihat layar",
        "lihat layarku",
        "lihat layar aku",
        "lihat screen",
        "lihat desktop",
        "lihat tampilan",
        "lihat yang ada di layar",
        "apa yang kamu lihat",
        "apa yang kau lihat",
        "apa yang terlihat",
        "apa yang ada di layar",
        "apa isi layar",
        "baca layar",
        "baca screen",
        "baca yang ada di layar",
        "ceritain apa yang kamu lihat",
        "ceritakan apa yang kamu lihat",
        "cek layar",
        "periksa layar",
        "analisis layar",
        "analisa layar"
    )

    if any(
        phrase in text
        for phrase in direct_phrases
    ):
        return True

    screen_words = (
        "layar",
        "screen",
        "desktop",
        "tampilan"
    )

    visual_words = (
        "lihat",
        "baca",
        "cek",
        "periksa",
        "analisis",
        "analisa",
        "cari",
        "temukan",
        "apa"
    )

    has_screen_word = any(
        word in text
        for word in screen_words
    )

    has_visual_word = any(
        word in text
        for word in visual_words
    )

    return (
        has_screen_word
        and
        has_visual_word
    )


# =========================================================
# TOOL RESULT HELPERS
# =========================================================

def has_successful_tool(
    results,
    tool_name
):

    for item in results:

        if (
            item.get("tool") == tool_name
            and
            item.get("success")
        ):
            return True

    return False


def has_failed_tool(
    results,
    tool_name
):

    for item in results:

        if (
            item.get("tool") == tool_name
            and
            not item.get("success")
        ):
            return True

    return False


def has_attempted_tool(
    results,
    tool_name
):

    for item in results:

        if item.get(
            "tool"
        ) == tool_name:
            return True

    return False


# =========================================================
# TOOL PAYLOAD
# =========================================================

def get_tool_payload(item):

    if not isinstance(
        item,
        dict
    ):
        return {}

    nested = item.get(
        "result"
    )

    if isinstance(
        nested,
        dict
    ):
        return nested

    return item


# =========================================================
# VERIFIED ACTION
# =========================================================

def tool_result_is_verified(item):

    if not isinstance(
        item,
        dict
    ):
        return False

    if not item.get(
        "success"
    ):
        return False

    payload = get_tool_payload(
        item
    )

    if payload.get(
        "verified"
    ) is True:
        return True

    verification = payload.get(
        "verification"
    )

    if isinstance(
        verification,
        dict
    ):

        if verification.get(
            "verified"
        ) is True:
            return True

    ui_click_result = payload.get(
        "ui_click_result"
    )

    if isinstance(
        ui_click_result,
        dict
    ):

        verification = (
            ui_click_result.get(
                "verification"
            )
        )

        if isinstance(
            verification,
            dict
        ):

            if verification.get(
                "verified"
            ) is True:
                return True

    return False


def has_verified_action_success(
    results
):

    for item in results:

        tool_name = str(
            item.get(
                "tool"
            )
            or ""
        )

        if tool_name in OBSERVATION_TOOLS:
            continue

        if tool_result_is_verified(
            item
        ):
            return True

    return False


# =========================================================
# VISUAL PIPELINE ROUTER
# =========================================================

def get_forced_visual_actions(
    user_text,
    results
):

    if not is_visual_request(
        user_text
    ):
        return None

    # =====================================================
    # STEP 1 — SCREENSHOT
    # =====================================================

    if not has_successful_tool(
        results,
        "screen_capture"
    ):

        if has_failed_tool(
            results,
            "screen_capture"
        ):
            return None

        print(
            "[VISION ROUTER] "
            "Permintaan visual terdeteksi → "
            "mengambil screenshot baru."
        )

        return [
            {
                "tool": "screen_capture",
                "arguments": {
                    "mode": "latest"
                }
            }
        ]

    # =====================================================
    # STEP 2 — VISION
    # =====================================================

    if not has_successful_tool(
        results,
        "screen_vision"
    ):

        if has_failed_tool(
            results,
            "screen_vision"
        ):
            return None

        print(
            "[VISION ROUTER] "
            "Screenshot tersedia → "
            "menjalankan screen_vision."
        )

        instruction = (
            "Analisis screenshot desktop terbaru untuk "
            "menjawab permintaan user berikut:\n\n"
            f"{user_text}\n\n"
            "Gunakan hanya informasi yang benar-benar "
            "terlihat pada screenshot. "
            "Jangan mengarang elemen UI, window, teks, "
            "ikon, tombol, atau objek yang tidak terlihat. "
            "Jika tidak yakin, katakan tidak yakin. "
            "Jawab dalam Bahasa Indonesia."
        )

        return [
            {
                "tool": "screen_vision",
                "arguments": {
                    "instruction": instruction
                }
            }
        ]

    return None


# =========================================================
# CLEAN TARGET
# =========================================================

def _clean_target_suffixes(target):

    target = _clean_end_punctuation(
        target
    )

    suffix_patterns = (
        r"\s+yang\s+(?:sedang\s+)?terbuka\s*$",
        r"\s+yang\s+(?:sedang\s+)?aktif\s*$",
        r"\s+(?:dong|ya|yah|sekarang|deh|dah)\s*$"
    )

    changed = True

    while changed:

        changed = False

        for pattern in suffix_patterns:

            cleaned = re.sub(
                pattern,
                "",
                target,
                flags=re.IGNORECASE
            ).strip()

            if cleaned != target:

                target = cleaned
                changed = True

    return _clean_end_punctuation(
        target
    )


# =========================================================
# OPEN APP TARGET
# =========================================================

def extract_open_app_target(
    user_text
):
    """
    High-confidence parser untuk membuka aplikasi.

    Mendukung typo ringan pada kata kerja.

    Contoh:
    buka notepad
    buke notepad
    bukaa notepad
    open chrome
    """

    text = _prepare_command_text(
        user_text
    )

    if not text:
        return None

    # Multi-step jangan ditelan router satu aksi.
    if _has_sequence_connector(
        text
    ):
        return None

    first_word, rest = (
        _split_first_word(
            text
        )
    )

    match = _match_verb(
        first_word,
        OPEN_VERBS
    )

    if not match[
        "matched"
    ]:
        return None

    if (
        match["score"] < 1.0
        and
        match["candidate"]
    ):

        print(
            "[INTENT] "
            f"Kata '{first_word}' dikenali sebagai "
            f"'{match['candidate']}' "
            f"(score={match['score']:.2f})."
        )

    rest = str(
        rest or ""
    ).strip()

    # =====================================================
    # OPTIONAL APP PREFIX
    # =====================================================

    rest = re.sub(
        r"^(?:aplikasi|application|app|program)\s+",
        "",
        rest,
        flags=re.IGNORECASE
    ).strip()

    if not rest:
        return None

    # =====================================================
    # NON-APPLICATION OBJECTS
    # =====================================================

    blocked_prefixes = (
        "file ",
        "folder ",
        "website ",
        "situs ",
        "link ",
        "url "
    )

    lowered_rest = rest.lower()

    if any(
        lowered_rest.startswith(
            prefix
        )
        for prefix in blocked_prefixes
    ):
        return None

    target = _clean_target_suffixes(
        rest
    )

    if not target:
        return None

    if target.lower() in {
        "itu",
        "ini",
        "tersebut",
        "aplikasi",
        "app",
        "program"
    }:
        return None

    return target


# =========================================================
# WINDOW CLOSE TARGET
# =========================================================

def extract_window_close_target(
    user_text
):
    """
    High-confidence parser untuk menutup window.

    Mendukung:

    tutup notepad
    tutuo notepad
    tutp notepad
    tutup jendela notepad
    close window chrome
    keluar dari aplikasi notepad
    """

    text = _prepare_command_text(
        user_text
    )

    if not text:
        return None

    lower = text.lower()

    # =====================================================
    # MULTI-STEP REQUEST
    # =====================================================

    if _has_sequence_connector(
        text
    ):
        return None

    # =====================================================
    # AMBIGUOUS MULTI WINDOW REQUEST
    # =====================================================

    ambiguous_hints = (
        "sebelah kanan",
        "sebelah kiri",
        "yang kanan",
        "yang kiri",
        "paling kanan",
        "paling kiri",
        "jendela pertama",
        "jendela kedua",
        "window pertama",
        "window kedua",
        "semua jendela",
        "semua window",
        "semua aplikasi"
    )

    if any(
        hint in lower
        for hint in ambiguous_hints
    ):
        return None

    # =====================================================
    # "KELUAR DARI ..."
    # =====================================================

    keluar_match = re.match(
        r"^keluar\s+dari\s+(.+)$",
        text,
        flags=re.IGNORECASE
    )

    if keluar_match:

        rest = keluar_match.group(
            1
        ).strip()

    else:

        # =================================================
        # NORMAL / FUZZY CLOSE VERB
        # =================================================

        first_word, rest = (
            _split_first_word(
                text
            )
        )

        match = _match_verb(
            first_word,
            CLOSE_VERBS
        )

        if not match[
            "matched"
        ]:
            return None

        if (
            match["score"] < 1.0
            and
            match["candidate"]
        ):

            print(
                "[INTENT] "
                f"Kata '{first_word}' dikenali sebagai "
                f"'{match['candidate']}' "
                f"(score={match['score']:.2f})."
            )

    rest = str(
        rest or ""
    ).strip()

    # =====================================================
    # OPTIONAL WINDOW PREFIX
    # =====================================================

    rest = re.sub(
        r"^(?:jendela|window|aplikasi|application|app)\s+",
        "",
        rest,
        flags=re.IGNORECASE
    ).strip()

    if not rest:
        return None

    # "tutup semua notepad" jangan menutup satu secara acak.
    if rest.lower().startswith(
        "semua "
    ):
        return None

    target = _clean_target_suffixes(
        rest
    )

    if not target:
        return None

    if target.lower() in {
        "itu",
        "ini",
        "tersebut",
        "yang terbuka",
        "yang aktif"
    }:
        return None

    return target


# =========================================================
# VISUAL CLICK TARGET
# =========================================================

def extract_ui_click_target(
    user_text
):

    text = _prepare_command_text(
        user_text
    )

    lower = text.lower()

    # Multi-step ditangani LLM.
    if _has_sequence_connector(
        text
    ):
        return None

    # =====================================================
    # RAW COORDINATE CLICK
    # =====================================================

    if any(
        hint in lower
        for hint in ABSOLUTE_MOUSE_HINTS
    ):
        return None

    # =====================================================
    # SPECIAL CLICK TYPES
    # =====================================================

    forbidden = (
        "klik kanan",
        "right click",
        "right-click",
        "double click",
        "double-click",
        "klik dua kali",
        "middle click",
        "klik tengah"
    )

    if any(
        hint in lower
        for hint in forbidden
    ):
        return None

    ui_hints = (
        "tombol",
        "button",
        "ikon",
        "icon",
        "menu",
        "kolom",
        "field",
        "textbox",
        "link",
        "tab",
        "checkbox",
        "dropdown"
    )

    if not any(
        hint in lower
        for hint in ui_hints
    ):
        return None

    # =====================================================
    # NORMAL CLICK
    # =====================================================

    match = re.search(
        r"\b(?:klik|click|tekan|pencet)\b\s+(.+)",
        text,
        flags=re.IGNORECASE
    )

    if not match:
        return None

    target = match.group(
        1
    ).strip()

    target = _clean_end_punctuation(
        target
    )

    if not target:
        return None

    return target


# =========================================================
# SPECIALIZED ACTION ROUTER
# =========================================================

def get_forced_specialized_actions(
    user_text,
    results
):
    """
    Prioritaskan skill spesifik yang SUDAH ADA.
    """

    # =====================================================
    # OPEN APPLICATION
    # =====================================================

    open_target = (
        extract_open_app_target(
            user_text
        )
    )

    if (
        open_target
        and
        registry.has_tool(
            "open_app"
        )
        and
        not has_attempted_tool(
            results,
            "open_app"
        )
    ):

        print(
            "[SKILL ROUTER] "
            "Intent buka aplikasi terdeteksi → "
            "menggunakan open_app langsung."
        )

        return [
            {
                "tool": "open_app",
                "arguments": {
                    "app_name": open_target
                }
            }
        ]

    # =====================================================
    # WINDOW CLOSE
    # =====================================================

    close_target = (
        extract_window_close_target(
            user_text
        )
    )

    if (
        close_target
        and
        registry.has_tool(
            "window_close"
        )
        and
        not has_attempted_tool(
            results,
            "window_close"
        )
    ):

        print(
            "[SKILL ROUTER] "
            "Intent tutup window terdeteksi → "
            "menggunakan window_close langsung."
        )

        return [
            {
                "tool": "window_close",
                "arguments": {
                    "title": close_target,
                    "verify": True
                }
            }
        ]

    # =====================================================
    # VISUAL UI CLICK
    # =====================================================

    click_target = (
        extract_ui_click_target(
            user_text
        )
    )

    if (
        click_target
        and
        registry.has_tool(
            "ui_click"
        )
        and
        not has_attempted_tool(
            results,
            "ui_click"
        )
    ):

        print(
            "[SKILL ROUTER] "
            "Intent klik elemen UI terdeteksi → "
            "menggunakan ui_click langsung."
        )

        return [
            {
                "tool": "ui_click",
                "arguments": {
                    "target": click_target,
                    "verify": True
                }
            }
        ]

    return None


# =========================================================
# MOUSE REQUEST TYPE
# =========================================================

def is_relative_mouse_request(user_text):

    text = str(
        user_text or ""
    ).lower()

    if any(
        hint in text
        for hint in ABSOLUTE_MOUSE_HINTS
    ):
        return False

    return any(
        hint in text
        for hint in RELATIVE_MOUSE_HINTS
    )


# =========================================================
# EXTRACT PIXEL AMOUNT
# =========================================================

def extract_pixel_amount(user_text):

    text = str(
        user_text or ""
    ).lower()

    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:pixel|pixels|px)",
        text
    )

    if not match:
        return None

    try:

        value = float(
            match.group(1)
        )

        if value.is_integer():
            return int(
                value
            )

        return value

    except ValueError:

        return None


# =========================================================
# NORMALIZE MOUSE ACTIONS
# =========================================================

def normalize_mouse_actions(
    actions,
    user_text
):

    if not actions:
        return actions

    text = str(
        user_text or ""
    ).lower()

    relative_request = (
        is_relative_mouse_request(
            user_text
        )
    )

    pixel_amount = (
        extract_pixel_amount(
            user_text
        )
    )

    normalized = []

    for action in actions:

        if not isinstance(
            action,
            dict
        ):

            normalized.append(
                action
            )

            continue

        tool_name = str(
            action.get("tool")
            or ""
        )

        arguments = action.get(
            "arguments",
            {}
        )

        if not isinstance(
            arguments,
            dict
        ):
            arguments = {}

        arguments = dict(
            arguments
        )

        # =================================================
        # MOUSE CONTROL
        # =================================================

        if tool_name == "mouse_control":

            mouse_action = str(
                arguments.get("action")
                or ""
            ).lower()

            # ---------------------------------------------
            # ABSOLUTE -> RELATIVE CORRECTION
            # ---------------------------------------------

            if (
                relative_request
                and
                mouse_action == "move"
            ):

                print(
                    "[AGENT GUARD] "
                    "Gerakan mouse dikoreksi "
                    "dari move menjadi move_relative."
                )

                arguments[
                    "action"
                ] = "move_relative"

                mouse_action = (
                    "move_relative"
                )

            # ---------------------------------------------
            # DIRECTION NORMALIZATION
            # ---------------------------------------------

            if (
                relative_request
                and
                mouse_action == "move_relative"
            ):

                if pixel_amount is not None:

                    if "ke kanan" in text:

                        arguments["x"] = abs(
                            pixel_amount
                        )

                        arguments["y"] = 0

                    elif "ke kiri" in text:

                        arguments["x"] = -abs(
                            pixel_amount
                        )

                        arguments["y"] = 0

                    elif "ke bawah" in text:

                        arguments["x"] = 0

                        arguments["y"] = abs(
                            pixel_amount
                        )

                    elif "ke atas" in text:

                        arguments["x"] = 0

                        arguments["y"] = -abs(
                            pixel_amount
                        )

                else:

                    try:

                        x_value = int(
                            arguments.get(
                                "x",
                                0
                            )
                            or 0
                        )

                    except (
                        TypeError,
                        ValueError
                    ):

                        x_value = 0

                    try:

                        y_value = int(
                            arguments.get(
                                "y",
                                0
                            )
                            or 0
                        )

                    except (
                        TypeError,
                        ValueError
                    ):

                        y_value = 0

                    if "ke kanan" in text:

                        amount = max(
                            abs(x_value),
                            abs(y_value)
                        )

                        arguments["x"] = amount
                        arguments["y"] = 0

                    elif "ke kiri" in text:

                        amount = max(
                            abs(x_value),
                            abs(y_value)
                        )

                        arguments["x"] = -amount
                        arguments["y"] = 0

                    elif "ke bawah" in text:

                        amount = max(
                            abs(x_value),
                            abs(y_value)
                        )

                        arguments["x"] = 0
                        arguments["y"] = amount

                    elif "ke atas" in text:

                        amount = max(
                            abs(x_value),
                            abs(y_value)
                        )

                        arguments["x"] = 0
                        arguments["y"] = -amount

        normalized.append({
            "tool": tool_name,
            "arguments": arguments
        })

    return normalized


# =========================================================
# REAL ACTION SUCCESS
# =========================================================

def has_real_action_success(results):

    for item in results:

        if not item.get(
            "success"
        ):
            continue

        tool_name = str(
            item.get("tool")
            or ""
        )

        if (
            tool_name
            not in OBSERVATION_TOOLS
        ):
            return True

    return False


# =========================================================
# EXPLICIT SKILL CREATION REQUEST
# =========================================================

def is_explicit_skill_creation_request(
    user_text
):

    text = str(
        user_text or ""
    ).lower()

    phrases = (
        "buat skill",
        "bikin skill",
        "buatkan skill",
        "bikinin skill",
        "belajar cara",
        "pelajari cara",
        "buat kemampuan",
        "bikin kemampuan",
        "tambahkan kemampuan",
        "tambah kemampuan"
    )

    return any(
        phrase in text
        for phrase in phrases
    )


# =========================================================
# EXPLICIT SKILL REPAIR REQUEST
# =========================================================

def is_explicit_skill_repair_request(
    user_text
):

    text = str(
        user_text or ""
    ).lower()

    phrases = (
        "perbaiki skill",
        "betulkan skill",
        "repair skill",
        "fix skill",
        "perbaiki kemampuan",
        "betulkan kemampuan"
    )

    return any(
        phrase in text
        for phrase in phrases
    )


# =========================================================
# REDUNDANT OBSERVATION GUARD
# =========================================================

def _arguments_key(arguments):

    if not isinstance(
        arguments,
        dict
    ):
        arguments = {}

    try:

        return json.dumps(
            arguments,
            sort_keys=True,
            ensure_ascii=False
        )

    except Exception:

        return str(
            arguments
        )


def is_redundant_observation_action(
    action,
    previous_actions,
    previous_results
):

    if not isinstance(
        action,
        dict
    ):
        return False

    tool_name = str(
        action.get(
            "tool"
        )
        or ""
    )

    if tool_name not in OBSERVATION_TOOLS:
        return False

    args_key = _arguments_key(
        action.get(
            "arguments",
            {}
        )
    )

    max_index = min(
        len(previous_actions),
        len(previous_results)
    )

    for index in range(
        max_index - 1,
        -1,
        -1
    ):

        old_action = previous_actions[
            index
        ]

        old_result = previous_results[
            index
        ]

        if not old_result.get(
            "success"
        ):
            continue

        old_tool = str(
            old_action.get(
                "tool"
            )
            or ""
        )

        # Ada action sesudah observation lama.
        # Observation lama boleh dianggap stale.
        if old_tool not in OBSERVATION_TOOLS:
            return False

        if old_tool != tool_name:
            continue

        old_args_key = _arguments_key(
            old_action.get(
                "arguments",
                {}
            )
        )

        if old_args_key == args_key:
            return True

    return False


# =========================================================
# ACTION SANITIZER
# =========================================================

def sanitize_planned_actions(
    actions,
    user_text,
    previous_actions,
    previous_results
):

    if not actions:

        return (
            actions,
            []
        )

    cleaned = []
    notes = []

    explicit_skill_creation = (
        is_explicit_skill_creation_request(
            user_text
        )
    )

    explicit_skill_repair = (
        is_explicit_skill_repair_request(
            user_text
        )
    )

    real_action_done = (
        has_real_action_success(
            previous_results
        )
    )

    for action in actions:

        if not isinstance(
            action,
            dict
        ):
            continue

        tool_name = str(
            action.get(
                "tool"
            )
            or ""
        ).strip()

        if not tool_name:
            continue

        # =================================================
        # INVENTED / UNKNOWN TOOL GUARD
        # =================================================

        if not registry.has_tool(
            tool_name
        ):

            registry.reload()

        if not registry.has_tool(
            tool_name
        ):

            print(
                "[AGENT GUARD] "
                f"Tool tidak tersedia diblok: "
                f"{tool_name}"
            )

            notes.append(
                f"Tool '{tool_name}' tidak tersedia. "
                f"Jangan mengarang nama tool. "
                f"Pilih tool yang benar-benar ada."
            )

            continue

        # =================================================
        # DUPLICATE OBSERVATION
        # =================================================

        if is_redundant_observation_action(
            action,
            previous_actions,
            previous_results
        ):

            print(
                "[AGENT GUARD] "
                f"Observation {tool_name} identik "
                f"diblok karena belum ada perubahan desktop."
            )

            notes.append(
                f"Jangan ulangi {tool_name} dengan "
                f"argument yang sama karena hasilnya masih fresh."
            )

            continue

        # =================================================
        # MANUAL REPAIR LOOP GUARD
        # =================================================

        # Tool failure normal sudah ditangani oleh
        # attempt_recovery().
        #
        # Agent tidak perlu memanggil repair_skill sendiri
        # kecuali USER memang meminta repair skill.
        if (
            tool_name == "repair_skill"
            and
            not explicit_skill_repair
        ):

            print(
                "[AGENT GUARD] "
                "Pemanggilan repair_skill manual diblok."
            )

            notes.append(
                "Jangan memanggil repair_skill manual untuk "
                "kegagalan tool biasa. Auto-recovery sudah "
                "menangani diagnosis dan repair. "
                "Pilih pemanggilan tool yang benar."
            )

            continue

        # =================================================
        # CREATE SKILL AFTER ACTION SUCCEEDED
        # =================================================

        if (
            tool_name == "create_skill"
            and
            real_action_done
            and
            not explicit_skill_creation
        ):

            print(
                "[AGENT GUARD] "
                "create_skill diblok karena aksi nyata "
                "sudah berhasil."
            )

            notes.append(
                "Jangan membuat skill baru karena "
                "tool yang tersedia sudah berhasil "
                "melakukan aksi request saat ini."
            )

            continue

        cleaned.append(
            action
        )

    return (
        cleaned,
        notes
    )


# =========================================================
# SYSTEM PROMPT
# =========================================================

def build_agent_system(
    system_prompt,
    memory_context
):

    tools = registry.list_tools()

    tool_text = json.dumps(
        tools,
        indent=2,
        ensure_ascii=False
    )

    return f"""
{system_prompt}

{memory_context}

Kamu juga merupakan autonomous desktop agent Windows.


=========================================================
TOOL YANG TERSEDIA
=========================================================

{tool_text}


=========================================================
PRIORITAS PEMILIHAN TOOL
=========================================================

SELALU prioritaskan TOOL YANG SUDAH TERSEDIA.

Pilih tool dengan level kemampuan PALING SPESIFIK
yang langsung menyelesaikan tujuan user.


Contoh:

- membuka aplikasi
  → open_app

- menutup window
  → window_close

- klik tombol / icon / menu
  → ui_click

- mencari koordinat UI tanpa klik
  → screen_locate

- mouse mentah
  → mouse_control

- fokus window
  → focus_window

- mengetik
  → type_text / keyboard_control

- melihat isi layar
  → screen_capture + screen_vision


Jika user berkata:

"buka Notepad"

gunakan:

{{
  "tool": "open_app",
  "arguments": {{
    "app_name": "Notepad"
  }}
}}


JANGAN mengarang:

window_open
launch_app
start_application


Jika user berkata:

"tutup Notepad"

atau:

"tutup jendela Notepad"

gunakan window_close.


TYPO RINGAN user boleh terjadi.

Contoh:

"buke notepad"

"tutuo notepad"

Jangan karena typo lalu mengarang tool baru.

Gunakan maksud user dan tool yang benar-benar tersedia.


Jika user memberikan beberapa tindakan:

"buka Notepad terus ketik halo"

jangan menganggap seluruh kalimat sebagai nama aplikasi.

Lakukan bertahap:

open_app
→ tunggu hasil
→ tool ketik yang sesuai


=========================================================
ATURAN CREATE_SKILL
=========================================================

create_skill adalah LAST RESORT.

Gunakan hanya jika:

1. user memang meminta membuat / mempelajari skill

ATAU

2. kemampuan benar-benar belum tersedia.


Jangan membuat ulang kemampuan yang sudah ada.


=========================================================
ATURAN REPAIR
=========================================================

Kegagalan tool biasa sudah melewati AUTO RECOVERY.

Jangan memanggil repair_skill berulang-ulang sendiri
hanya karena tool gagal.

Jika error adalah salah argument/schema caller,
perbaiki PEMANGGILAN tool.

Jangan menganggap source skill rusak.

repair_skill manual hanya digunakan jika user
memang meminta memperbaiki suatu skill.


=========================================================
HINDARI OBSERVATION BERULANG
=========================================================

Jangan:

screen_state {{}}
screen_state {{}}
screen_state {{}}

jika belum ada perubahan desktop.


Jika action tool memberi:

verified = true

atau:

verification.verified = true

itu adalah bukti kuat aksi berhasil.

Jangan verification ulang tanpa alasan.


Jika open_app sukses pada request sederhana seperti:

"buka Notepad"

tidak perlu screen_state hanya untuk memastikan
Notepad terbuka kecuali memang ada alasan atau user
meminta verifikasi tambahan.


=========================================================
PRINSIP UTAMA
=========================================================

LIHAT
→ PIKIR
→ BERTINDAK
→ LIHAT HASIL
→ PIKIR LAGI
→ SELESAI


REQUEST USER SAAT INI adalah tugas BARU.

Hasil request sebelumnya bukan bukti bahwa
request sekarang selesai.


=========================================================
PERCEPTION
=========================================================

screen_state:

metadata Windows.

screen_capture:

screenshot.

screen_vision:

memahami screenshot.

screen_locate:

mencari koordinat UI tanpa klik.


screen_state BUKAN vision.


Jika user meminta:

"lihat layar"

"apa yang kamu lihat"

"baca layar"

gunakan:

screen_capture
→ screen_vision


=========================================================
OBSERVATION VS ACTION
=========================================================

Observation tools:

- screen_state
- screen_capture
- screen_vision
- screen_locate


Observation bukan tindakan nyata.


=========================================================
GERAKAN MOUSE
=========================================================

GERAK ABSOLUT:

mouse_control
action = move


GERAK RELATIF:

mouse_control
action = move_relative


kanan:
x positif

kiri:
x negatif

bawah:
y positif

atas:
y negatif


Contoh:

"geser 300 pixel ke kanan"

BENAR:

{{
  "tool": "mouse_control",
  "arguments": {{
    "action": "move_relative",
    "x": 300,
    "y": 0
  }}
}}


JANGAN:

{{
  "tool": "mouse_control",
  "arguments": {{
    "action": "move",
    "x": 300,
    "y": 0
  }}
}}


=========================================================
ATURAN TOOL
=========================================================

1. Kalau hanya ngobrol, jangan gunakan tool.

2. Kalau meminta tindakan komputer, gunakan tool.

3. Jangan mengarang nama tool.

4. Argument harus sesuai schema.

5. Prioritaskan tool paling spesifik.

6. Jangan memakai tool generik jika tool khusus tersedia.

7. Jika aksi bergantung pada hasil sebelumnya,
   lakukan bertahap.

8. Jangan menebak hasil tool.

9. Observation bukan action.

10. Jangan mengaku berhasil sebelum action sukses.

11. Jangan mengulang error tanpa alasan.

12. create_skill adalah last resort.

13. repair_skill manual bukan respons default terhadap
    kegagalan tool.

14. Auto-recovery menangani bug skill.

15. screen_state hanya jika metadata diperlukan.

16. screen_capture + screen_vision untuk visual.

17. Jangan mengarang elemen visual.

18. Jangan screenshot berulang tanpa kebutuhan.

19. verified=true berarti aksi sudah diverifikasi.

20. Jangan mengarang window_open jika open_app tersedia.

21. Jangan mengarang tool jika nama tool tidak ada
    pada daftar TOOL.

22. Jika user typo ringan, pahami intentnya tanpa
    membuat tool baru.


=========================================================
FORMAT OUTPUT
=========================================================

Balas HANYA JSON valid:

{{
  "reply": "",
  "actions": [
    {{
      "tool": "nama_tool",
      "arguments": {{}}
    }}
  ],
  "done": false
}}


Jika selesai:

{{
  "reply": "jawaban natural Pochi",
  "actions": [],
  "done": true
}}


Jika hanya ngobrol:

{{
  "reply": "jawaban natural Pochi",
  "actions": [],
  "done": true
}}


Jika actions masih ada:

done HARUS false.
"""


# =========================================================
# PLAN PARSER
# =========================================================

def parse_plan(raw):

    try:

        data = json.loads(
            raw
        )

    except json.JSONDecodeError:

        return {
            "reply": (
                "Aku gagal membaca rencana aksiku."
            ),
            "actions": [],
            "done": True
        }

    reply = str(
        data.get("reply")
        or ""
    ).strip()

    actions = data.get(
        "actions",
        []
    )

    if not isinstance(
        actions,
        list
    ):
        actions = []

    cleaned_actions = []

    for action in actions[
        :MAX_ACTIONS_PER_STEP
    ]:

        if not isinstance(
            action,
            dict
        ):
            continue

        tool_name = str(
            action.get("tool")
            or ""
        ).strip()

        arguments = action.get(
            "arguments",
            {}
        )

        if not isinstance(
            arguments,
            dict
        ):
            arguments = {}

        if not tool_name:
            continue

        cleaned_actions.append({
            "tool": tool_name,
            "arguments": arguments
        })

    done = bool(
        data.get(
            "done",
            False
        )
    )

    if cleaned_actions:
        done = False

    return {
        "reply": reply,
        "actions": cleaned_actions,
        "done": done
    }


# =========================================================
# EXECUTE ONE ACTION
# =========================================================

def execute_one_action(
    tool_name,
    arguments
):

    if not registry.has_tool(
        tool_name
    ):

        registry.reload()

    if not registry.has_tool(
        tool_name
    ):

        return {
            "tool": tool_name,
            "success": False,
            "error": (
                f"Tool '{tool_name}' "
                f"tidak tersedia."
            )
        }

    print(
        f"[TOOL] Menjalankan "
        f"{tool_name}..."
    )

    result = registry.run_tool(
        tool_name,
        arguments
    )

    # =====================================================
    # SUCCESS
    # =====================================================

    if result.get(
        "success"
    ):

        return {
            "tool": tool_name,
            **result
        }

    # =====================================================
    # FAILED
    # =====================================================

    error = str(
        result.get(
            "error",
            "Unknown error"
        )
    )

    print(
        f"[TOOL ERROR] "
        f"{tool_name}: {error}"
    )

    # =====================================================
    # AUTO RECOVERY
    # =====================================================

    try:

        recovery = attempt_recovery(
            tool_name=tool_name,
            arguments=arguments,
            error=error
        )

    except Exception as recovery_error:

        recovery = {
            "attempted": False,
            "recovered": False,
            "reason": (
                "Recovery system error: "
                + str(
                    recovery_error
                )
            )
        }

    # =====================================================
    # RECOVERED
    # =====================================================

    if recovery.get(
        "recovered"
    ):

        retry = recovery.get(
            "retry_result",
            {}
        )

        print(
            f"[AUTO RECOVERY SUCCESS] "
            f"{tool_name}"
        )

        return {
            "tool": tool_name,
            **retry,
            "auto_recovery": {
                "attempted": True,
                "recovered": True,
                "reason": recovery.get(
                    "reason",
                    ""
                )
            }
        }

    # =====================================================
    # NOT RECOVERED
    # =====================================================

    return {
        "tool": tool_name,
        **result,
        "auto_recovery": {
            "attempted": recovery.get(
                "attempted",
                False
            ),
            "recovered": False,
            "reason": recovery.get(
                "reason",
                ""
            )
        }
    }


# =========================================================
# EXECUTE ACTIONS
# =========================================================

def execute_actions(actions):

    results = []

    for action in actions:

        result = execute_one_action(
            action["tool"],
            action["arguments"]
        )

        results.append(
            result
        )

        time.sleep(
            ACTION_DELAY
        )

    return results


# =========================================================
# AGENT LOOP
# =========================================================

def run_agent(
    user_text,
    system_prompt,
    memory_context,
    history=None
):

    registry.reload()

    if history is None:
        history = []

    current_is_action = (
        is_action_request(
            user_text
        )
    )

    current_is_visual = (
        is_visual_request(
            user_text
        )
    )

    working_messages = list(
        history[
            -MAX_HISTORY_MESSAGES:
        ]
    )

    working_messages.append({
        "role": "user",
        "content": (
            "REQUEST USER SAAT INI:\n"
            + user_text
            + "\n\n"
            "Ini adalah request baru. "
            "Jangan menganggap aksi dari percakapan "
            "sebelumnya sudah memenuhi request ini."
        )
    })

    all_actions = []
    all_results = []

    final_reply = ""

    # =====================================================
    # REASON → ACT → OBSERVE
    # =====================================================

    for step in range(
        1,
        MAX_AGENT_STEPS + 1
    ):

        print(
            f"[AGENT] Langkah "
            f"{step}/{MAX_AGENT_STEPS}..."
        )

        actions = None

        plan = {
            "reply": "",
            "actions": [],
            "done": False
        }

        # =================================================
        # 1. VISUAL ROUTER
        # =================================================

        forced_visual_actions = (
            get_forced_visual_actions(
                user_text,
                all_results
            )
        )

        if forced_visual_actions:

            actions = (
                forced_visual_actions
            )

            plan = {
                "reply": "",
                "actions": actions,
                "done": False
            }

        # =================================================
        # 2. SPECIALIZED ROUTER
        # =================================================

        if actions is None:

            forced_specialized_actions = (
                get_forced_specialized_actions(
                    user_text,
                    all_results
                )
            )

            if forced_specialized_actions:

                actions = (
                    forced_specialized_actions
                )

                plan = {
                    "reply": "",
                    "actions": actions,
                    "done": False
                }

        # =================================================
        # 3. NORMAL LLM DECISION
        # =================================================

        if actions is None:

            system_content = (
                build_agent_system(
                    system_prompt,
                    memory_context
                )
            )

            messages = [
                {
                    "role": "system",
                    "content": system_content
                }
            ]

            messages.extend(
                working_messages
            )

            print(
                "[AGENT] Membuat keputusan..."
            )

            response = agent_json(
                messages
            )

            print(
                "[AGENT] Keputusan selesai."
            )

            raw = response[
                "message"
            ][
                "content"
            ].strip()

            plan = parse_plan(
                raw
            )

            actions = plan[
                "actions"
            ]

            # =============================================
            # NORMALIZE MOUSE
            # =============================================

            actions = normalize_mouse_actions(
                actions,
                user_text
            )

            # =============================================
            # PLAN GUARDS
            # =============================================

            actions, guard_notes = (
                sanitize_planned_actions(
                    actions,
                    user_text,
                    all_actions,
                    all_results
                )
            )

            if guard_notes:

                working_messages.append({
                    "role": "user",
                    "content": (
                        "KOREKSI SISTEM:\n"
                        + "\n".join(
                            f"- {note}"
                            for note in guard_notes
                        )
                        + "\n\n"
                        "Pilih langkah lain yang benar-benar "
                        "dibutuhkan untuk tujuan user."
                    )
                })

        # =================================================
        # MODEL MAU SELESAI
        # =================================================

        if not actions:

            visual_capture_failed = (
                has_failed_tool(
                    all_results,
                    "screen_capture"
                )
            )

            visual_analysis_failed = (
                has_failed_tool(
                    all_results,
                    "screen_vision"
                )
            )

            visual_failed = (
                visual_capture_failed
                or
                visual_analysis_failed
            )

            vision_succeeded = (
                has_successful_tool(
                    all_results,
                    "screen_vision"
                )
            )

            # ---------------------------------------------
            # VISION GUARD
            # ---------------------------------------------

            if (
                current_is_visual
                and
                not vision_succeeded
                and
                not visual_failed
            ):

                print(
                    "[VISION GUARD] "
                    "Agent mencoba selesai "
                    "padahal belum benar-benar melihat layar."
                )

                working_messages.append({
                    "role": "user",
                    "content": (
                        "KOREKSI SISTEM:\n"
                        "User meminta informasi VISUAL layar, "
                        "tetapi screen_vision belum berhasil.\n\n"
                        "screen_state saja TIDAK CUKUP.\n"
                        "Gunakan screenshot + vision sebelum "
                        "menjawab isi visual layar."
                    )
                })

                continue

            # ---------------------------------------------
            # ACTION GUARD
            # ---------------------------------------------

            if (
                current_is_action
                and
                not has_real_action_success(
                    all_results
                )
                and
                not (
                    current_is_visual
                    and
                    visual_failed
                )
            ):

                print(
                    "[AGENT GUARD] "
                    "Model mencoba menyelesaikan tugas "
                    "padahal belum ada aksi nyata yang sukses."
                )

                working_messages.append({
                    "role": "user",
                    "content": (
                        "KOREKSI SISTEM:\n"
                        "Request user meminta AKSI nyata, "
                        "tetapi belum ada action tool "
                        "yang berhasil.\n\n"
                        "Pilih TOOL PALING SPESIFIK "
                        "yang sudah tersedia.\n"
                        "Jangan mengarang nama tool.\n"
                        "Jangan create_skill jika kemampuan "
                        "sudah tersedia.\n"
                        "Jangan memanggil repair_skill manual "
                        "untuk error pemanggilan biasa.\n\n"
                        f"TUJUAN USER:\n{user_text}"
                    )
                })

                continue

            # ---------------------------------------------
            # VALID FINAL
            # ---------------------------------------------

            final_reply = (
                plan.get(
                    "reply"
                )
                or "Oke."
            )

            break

        # =================================================
        # EXECUTE
        # =================================================

        step_results = execute_actions(
            actions
        )

        all_actions.extend(
            actions
        )

        all_results.extend(
            step_results
        )

        # =================================================
        # SAVE ATTEMPT
        # =================================================

        working_messages.append({
            "role": "assistant",
            "content": json.dumps(
                {
                    "actions": actions,
                    "done": False
                },
                ensure_ascii=False
            )
        })

        # =================================================
        # OBSERVATION
        # =================================================

        successful_tools = [
            item.get("tool")
            for item in all_results
            if item.get("success")
        ]

        verified_action = (
            has_verified_action_success(
                all_results
            )
        )

        observation = {
            "step": step,

            "current_user_goal": user_text,

            "tool_results": step_results,

            "successful_tools_this_request": (
                successful_tools
            ),

            "real_action_has_succeeded": (
                has_real_action_success(
                    all_results
                )
            ),

            "verified_action_has_succeeded": (
                verified_action
            ),

            "vision_has_succeeded": (
                has_successful_tool(
                    all_results,
                    "screen_vision"
                )
            )
        }

        extra_instruction = ""

        if verified_action:

            extra_instruction = (
                "\n\nPENTING:\n"
                "Salah satu action tool sudah memberikan "
                "VERIFIED = TRUE.\n"
                "Jika itu memenuhi tujuan user, "
                "jangan lakukan verification tambahan.\n"
                "Jawab bahwa tugas selesai."
            )

        working_messages.append({
            "role": "user",
            "content": (
                "HASIL TOOL / OBSERVATION:\n"
                + json.dumps(
                    observation,
                    indent=2,
                    ensure_ascii=False
                )
                + "\n\n"
                "TUJUAN USER SAAT INI:\n"
                + user_text
                + "\n\n"
                "Gunakan hanya hasil nyata di atas.\n"
                "Jangan menggunakan keberhasilan dari "
                "percakapan sebelumnya.\n"
                "Jika baru melakukan observation tetapi user "
                "meminta aksi, jalankan action tool berikutnya.\n"
                "Jika screen_vision berhasil, gunakan field "
                "'analysis' sebagai apa yang benar-benar "
                "terlihat di layar.\n"
                "Jangan mengarang elemen visual.\n"
                "Jangan mengatakan tugas selesai sebelum "
                "aksi yang diminta benar-benar sukses."
                + extra_instruction
            )
        })

    # =====================================================
    # MAX STEPS
    # =====================================================

    else:

        final_reply = (
            "Aku berhenti dulu karena langkah aksinya "
            "sudah terlalu banyak. Biar nggak muter terus."
        )

    if not final_reply:
        final_reply = "Oke."

    # =====================================================
    # RETURN
    # =====================================================

    return {
        "reply": final_reply,

        "plan": {
            "reply": final_reply,
            "actions": all_actions
        },

        "results": all_results
    }