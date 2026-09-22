import json
import re

from tool_registry import registry
from llm_runtime import fast_json


# =========================================================
# PROTECTED CORE TOOLS
# =========================================================

PROTECTED_TOOLS = {
    "create_skill",
    "repair_skill"
}


# =========================================================
# SAFETY / EXTERNAL ERRORS
# =========================================================

NON_REPAIRABLE_ERRORS = (
    "pyautogui fail-safe",
    "fail-safe triggered",
    "failsafe",

    "permission denied",
    "access is denied",

    "user cancelled",
    "user canceled",

    "not found",
    "tidak ditemukan"
)


# =========================================================
# TOOL INVOCATION / CONTRACT ERRORS
# =========================================================

INVOCATION_ERROR_PATTERNS = (
    r"unexpected keyword argument",

    r"missing \d+ required positional argument",

    r"missing required positional argument",

    r"missing \d+ required keyword-only argument",

    r"missing required keyword-only argument",

    r"got multiple values for argument",

    r"takes \d+ positional arguments? but \d+ were given",

    r"takes from \d+ to \d+ positional arguments? "
    r"but \d+ were given",

    r"takes \d+ positional arguments? "
    r"but \d+ was given",

    r"too many positional arguments",

    r"positional argument follows keyword argument"
)


# =========================================================
# VISION / MODEL OUTPUT ERRORS
# =========================================================

# Error jenis ini berarti:
#
# - model vision mengeluarkan JSON rusak
# - model mengeluarkan koordinat aneh
# - localization tidak yakin
# - output model tidak memenuhi kontrak
#
# Ini BUKAN bukti source Python skill rusak.
#
# screen_locate.py dan ui_click.py tidak boleh
# ditulis ulang gara-gara output model seperti ini.
VISION_OUTPUT_ERROR_PATTERNS = (
    r"vision tidak menghasilkan json",

    r"json vision tidak valid",

    r"output json model tidak valid",

    r"field found harus boolean",

    r"koordinat vision tidak valid",

    r"koordinat vision .* di luar gambar",

    r"vision mengatakan target ditemukan "
    r"tetapi koordinat tidak valid",

    r"deskripsi posisi vision tidak cocok",

    r"vision mengembalikan placeholder",

    r"vision mengembalikan koordinat contoh",

    r"confidence terlalu rendah",

    r"verifier vision tidak menghasilkan json",

    r"planner vision tidak menghasilkan json"
)


# =========================================================
# KNOWN NON-REPAIRABLE CHECK
# =========================================================

def is_known_non_repairable(
    error
):

    error_lower = str(
        error or ""
    ).lower()

    return any(
        text in error_lower
        for text in NON_REPAIRABLE_ERRORS
    )


# =========================================================
# TOOL INVOCATION ERROR CHECK
# =========================================================

def is_tool_invocation_error(
    error
):
    """
    Mendeteksi kegagalan kontrak pemanggilan tool.

    Kesalahan caller/agent tidak boleh menyebabkan
    source skill ditulis ulang.
    """

    error_text = str(
        error or ""
    ).lower()

    for pattern in (
        INVOCATION_ERROR_PATTERNS
    ):

        if re.search(
            pattern,
            error_text
        ):

            return True

    return False


# =========================================================
# VISION OUTPUT ERROR CHECK
# =========================================================

def is_vision_output_error(
    error
):
    """
    Mendeteksi kegagalan yang berasal dari output
    model vision/localization.

    Contoh:

    Vision tidak menghasilkan JSON.

    JSON vision tidak valid.

    Koordinat vision (1800,983)
    di luar gambar 1800x983.

    Error seperti ini BUKAN alasan untuk menulis ulang
    screen_locate.py atau ui_click.py.
    """

    error_text = str(
        error or ""
    ).lower()

    for pattern in (
        VISION_OUTPUT_ERROR_PATTERNS
    ):

        if re.search(
            pattern,
            error_text
        ):

            return True

    return False


# =========================================================
# DIAGNOSE FAILURE
# =========================================================

def analyze_failure(
    tool_name,
    arguments,
    error
):

    # =====================================================
    # HARD VISION / MODEL OUTPUT CHECK
    # =====================================================

    if is_vision_output_error(
        error
    ):

        return {
            "repairable": False,

            "reason": (
                "Kegagalan berasal dari output model vision "
                "atau hasil localization yang tidak memenuhi "
                "kontrak. Ini bukan bukti source code skill rusak."
            ),

            "desired_behavior": ""
        }

    # =====================================================
    # HARD SAFETY / EXTERNAL CHECK
    # =====================================================

    if is_known_non_repairable(
        error
    ):

        return {
            "repairable": False,

            "reason": (
                "Kegagalan berasal dari safety mechanism "
                "atau kondisi eksternal, bukan bug source code."
            ),

            "desired_behavior": ""
        }

    # =====================================================
    # HARD TOOL-CALL CONTRACT CHECK
    # =====================================================

    if is_tool_invocation_error(
        error
    ):

        return {
            "repairable": False,

            "reason": (
                "Kegagalan berasal dari argument/schema "
                "pemanggilan tool yang tidak cocok. "
                "Ini adalah kesalahan caller/agent, "
                "bukan alasan untuk mengubah source skill."
            ),

            "desired_behavior": ""
        }

    # =====================================================
    # LLM DIAGNOSIS
    # =====================================================

    prompt = f"""
Kamu adalah sistem diagnosis skill Pochi.

TOOL:
{tool_name}

ARGUMENT:
{json.dumps(arguments, ensure_ascii=False)}

ERROR:
{error}


Tentukan apakah error ini benar-benar berasal dari
BUG IMPLEMENTASI source code skill.


=========================================================
JANGAN REPAIR
=========================================================

JANGAN repair source code jika penyebabnya:

- PyAutoGUI fail-safe
- mekanisme keselamatan
- mouse berada di pojok fail-safe

- aplikasi tidak terinstall
- file tidak ditemukan
- window tidak ditemukan
- target tidak tersedia

- permission ditolak
- user membatalkan
- jaringan mati

- input user memang tidak valid

- caller / agent memberikan nama argument yang salah

- unexpected keyword argument

- required positional argument tidak diberikan

- required keyword-only argument tidak diberikan

- jumlah positional argument salah

- caller memberikan argument dua kali

- schema pemanggilan tool tidak cocok

- tool dipanggil dengan parameter yang tidak tercantum
  pada kontrak tool

- kondisi eksternal Windows


=========================================================
OUTPUT MODEL / VISION JUGA JANGAN REPAIR
=========================================================

JANGAN repair source skill jika error berasal dari
OUTPUT MODEL AI yang buruk atau tidak konsisten.

Contoh:

- vision tidak menghasilkan JSON

- JSON vision malformed

- JSON vision memakai quote/key yang salah

- model vision tidak menemukan target

- confidence vision rendah

- model memberikan koordinat di luar gambar

- koordinat model berada tepat di boundary gambar

- description vision tidak cocok dengan koordinat

- model mengembalikan placeholder

- UI navigation planner tidak yakin

- verifier vision tidak yakin

Kesalahan model inference seperti ini harus ditangani
sebagai kegagalan observasi / perception.

JANGAN menulis ulang ui_click.py atau screen_locate.py
hanya karena model vision memberikan output buruk.


=========================================================
SANGAT PENTING
=========================================================

Jika error terjadi karena AGENT salah memanggil fungsi,
maka AGENT yang harus memperbaiki pemanggilannya.

Jika error terjadi karena MODEL menghasilkan output buruk,
maka perception boleh retry atau menyerah dengan aman.

SOURCE SKILL TIDAK BOLEH DIREPAIR untuk dua kondisi itu.


=========================================================
BOLEH REPAIR
=========================================================

REPAIR hanya jika ada bukti bahwa implementasi skill
itu sendiri memang rusak, misalnya:

- syntax error di source skill

- NameError karena variabel source tidak ada

- import internal skill salah

- operasi internal menghasilkan exception karena
  implementasinya salah

- library digunakan secara salah DI DALAM skill

- algoritma skill benar-benar rusak

- fungsi skill tidak melakukan tujuan utamanya karena
  bug implementasi

- exception internal terjadi walaupun tool dipanggil
  menggunakan argument yang benar DAN output dependency
  yang diterimanya valid


Balas HANYA JSON:

{{
  "repairable": true,
  "reason": "alasan singkat",
  "desired_behavior": "perilaku yang benar"
}}
""".strip()

    print(
        "[RECOVERY] Mendiagnosis error..."
    )

    response = fast_json(
        [
            {
                "role": "user",
                "content": prompt
            }
        ],
        num_predict=220
    )

    print(
        "[RECOVERY] Diagnosis selesai."
    )

    raw = response[
        "message"
    ][
        "content"
    ].strip()

    # =====================================================
    # PARSE DIAGNOSIS
    # =====================================================

    try:

        data = json.loads(
            raw
        )

    except json.JSONDecodeError:

        return {
            "repairable": False,

            "reason": (
                "Diagnosis tidak menghasilkan JSON valid."
            ),

            "desired_behavior": ""
        }

    return {
        "repairable": bool(
            data.get(
                "repairable",
                False
            )
        ),

        "reason": str(
            data.get(
                "reason"
            )
            or ""
        ),

        "desired_behavior": str(
            data.get(
                "desired_behavior"
            )
            or ""
        )
    }


# =========================================================
# ATTEMPT RECOVERY
# =========================================================

def attempt_recovery(
    tool_name,
    arguments,
    error
):

    tool_name = str(
        tool_name or ""
    ).strip()

    if not isinstance(
        arguments,
        dict
    ):

        arguments = {}

    error = str(
        error or ""
    )

    # =====================================================
    # CORE PROTECTION
    # =====================================================

    if tool_name in PROTECTED_TOOLS:

        return {
            "attempted": False,

            "recovered": False,

            "reason": (
                "Tool inti dilindungi dari auto-repair."
            )
        }

    # =====================================================
    # TOOL CALL / SCHEMA ERROR
    # =====================================================

    if is_tool_invocation_error(
        error
    ):

        print(
            f"[RECOVERY] {tool_name} tidak direpair: "
            f"tool invocation/schema error."
        )

        return {
            "attempted": False,

            "recovered": False,

            "reason": (
                "Pemanggilan tool menggunakan argument/schema "
                "yang tidak cocok. Source skill tidak diubah; "
                "caller/agent harus memperbaiki pemanggilannya."
            )
        }

    # =====================================================
    # VISION / MODEL OUTPUT FAILURE
    # =====================================================

    # WAJIB sebelum diagnosis LLM.
    #
    # Kalau model vision menghasilkan JSON jelek,
    # source tool tidak boleh disentuh.
    if is_vision_output_error(
        error
    ):

        print(
            f"[RECOVERY] {tool_name} tidak direpair: "
            f"vision/model output error."
        )

        return {
            "attempted": False,

            "recovered": False,

            "reason": (
                "Output model vision/localization tidak valid "
                "atau tidak cukup yakin. Ini bukan kerusakan "
                "source skill, jadi source code tidak diubah."
            )
        }

    # =====================================================
    # SAFETY / EXTERNAL FAILURE
    # =====================================================

    if is_known_non_repairable(
        error
    ):

        print(
            f"[RECOVERY] {tool_name} tidak direpair: "
            f"safety/external condition."
        )

        return {
            "attempted": False,

            "recovered": False,

            "reason": (
                "Safety mechanism atau kondisi eksternal. "
                "Source code tidak diubah."
            )
        }

    # =====================================================
    # DIAGNOSIS
    # =====================================================

    diagnosis = analyze_failure(
        tool_name,
        arguments,
        error
    )

    if not diagnosis[
        "repairable"
    ]:

        print(
            f"[RECOVERY] {tool_name} tidak direpair: "
            f"{diagnosis['reason']}"
        )

        return {
            "attempted": False,

            "recovered": False,

            "reason": (
                diagnosis[
                    "reason"
                ]
            )
        }

    # =====================================================
    # FIND REPAIR TOOL
    # =====================================================

    if not registry.has_tool(
        "repair_skill"
    ):

        registry.reload()

    if not registry.has_tool(
        "repair_skill"
    ):

        return {
            "attempted": False,

            "recovered": False,

            "reason": (
                "repair_skill tidak tersedia."
            )
        }

    # =====================================================
    # REPAIR
    # =====================================================

    print(
        f"[AUTO RECOVERY] "
        f"Mencoba memperbaiki {tool_name}"
    )

    repair_result = registry.run_tool(
        "repair_skill",
        {
            "skill_name": tool_name,

            "problem": (
                f"{error}\n\n"
                f"Diagnosis:\n"
                f"{diagnosis['reason']}"
            ),

            "desired_behavior": (
                diagnosis[
                    "desired_behavior"
                ]
            )
        }
    )

    # =====================================================
    # REPAIR FAILED
    # =====================================================

    if not repair_result.get(
        "success"
    ):

        return {
            "attempted": True,

            "recovered": False,

            "reason": (
                "Repair gagal: "
                + str(
                    repair_result.get(
                        "error"
                    )
                )
            )
        }

    # =====================================================
    # RELOAD
    # =====================================================

    registry.reload()

    print(
        f"[AUTO RECOVERY] "
        f"{tool_name} diperbaiki. "
        f"Mencoba ulang..."
    )

    # =====================================================
    # ONE RETRY ONLY
    # =====================================================

    retry = registry.run_tool(
        tool_name,
        arguments
    )

    # =====================================================
    # RETRY SUCCESS
    # =====================================================

    if retry.get(
        "success"
    ):

        return {
            "attempted": True,

            "recovered": True,

            "reason": (
                "Skill berhasil diperbaiki "
                "dan retry berhasil."
            ),

            "retry_result": retry
        }

    # =====================================================
    # RETRY FAILED
    # =====================================================

    retry_error = str(
        retry.get(
            "error"
        )
        or ""
    )

    # =====================================================
    # RETRY BECAME CALLER ERROR
    # =====================================================

    if is_tool_invocation_error(
        retry_error
    ):

        return {
            "attempted": True,

            "recovered": False,

            "reason": (
                "Source skill sudah direpair, tetapi retry "
                "menunjukkan masalah argument/schema caller: "
                + retry_error
            ),

            "retry_result": retry
        }

    # =====================================================
    # RETRY BECAME VISION OUTPUT ERROR
    # =====================================================

    if is_vision_output_error(
        retry_error
    ):

        return {
            "attempted": True,

            "recovered": False,

            "reason": (
                "Retry gagal karena output model vision, "
                "bukan karena source skill: "
                + retry_error
            ),

            "retry_result": retry
        }

    # =====================================================
    # RETRY BECAME EXTERNAL / SAFETY ERROR
    # =====================================================

    if is_known_non_repairable(
        retry_error
    ):

        return {
            "attempted": True,

            "recovered": False,

            "reason": (
                "Retry gagal karena safety atau "
                "kondisi eksternal: "
                + retry_error
            ),

            "retry_result": retry
        }

    return {
        "attempted": True,

        "recovered": False,

        "reason": (
            "Skill sudah diperbaiki tetapi "
            "retry masih gagal: "
            + retry_error
        ),

        "retry_result": retry
    }