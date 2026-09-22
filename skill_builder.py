import ast
import os
import re
import shutil
from datetime import datetime

from llm_runtime import generate_code


# =========================================================
# PATH
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

SKILLS_DIR = os.path.join(
    BASE_DIR,
    "skills"
)

VERSIONS_DIR = os.path.join(
    BASE_DIR,
    "skill_versions"
)

os.makedirs(
    SKILLS_DIR,
    exist_ok=True
)

os.makedirs(
    VERSIONS_DIR,
    exist_ok=True
)


# =========================================================
# CONFIG
# =========================================================

MAX_GENERATION_ATTEMPTS = 3


# =========================================================
# GENERATOR PROMPT
# =========================================================

GENERATOR_PROMPT = """
Kamu adalah programmer untuk sistem skill Pochi,
AI desktop Windows berbasis Python.

Tugasmu membuat SATU skill Python yang dapat dimuat
secara otomatis oleh ToolRegistry Pochi.

FORMAT WAJIB:

def run(...):
    ...
    return {
        "message": "aksi benar-benar berhasil"
    }


TOOL = {
    "name": "nama_skill",
    "description": "deskripsi jelas",
    "parameters": {
        ...
    },
    "run": run
}


=========================================================
ATURAN ARSITEKTUR
=========================================================

1. Output HANYA source code Python.

2. Jangan gunakan markdown ```.

3. Jangan membuat main loop.

4. Jangan menggunakan input().

5. Jangan menjalankan aksi apa pun saat module di-import.

6. Semua tindakan aktif harus berada di dalam run()
   atau function yang dipanggil oleh run().

7. TOOL wajib memiliki:
   - name
   - description
   - parameters
   - run

8. Nama skill harus snake_case.

9. Jangan mengubah:
   - main.py
   - agent.py
   - tool_registry.py
   - memory.py
   - recovery.py
   - llm_runtime.py
   - skill_builder.py

10. Jangan mengubah skill lain.

11. Jangan menulis file lain kecuali memang merupakan
    fungsi utama skill tersebut.

12. Gunakan library standar Python jika memungkinkan.

13. Library eksternal boleh digunakan jika memang dibutuhkan.

14. Skill harus generik dan reusable.

15. Jangan hardcode hanya untuk satu contoh kalimat user.

16. Parameter TOOL harus cukup fleksibel agar skill dapat
    digunakan untuk permintaan lain yang sejenis.

17. Jangan membuat kemampuan palsu.
    Skill harus benar-benar melakukan aksi yang dijelaskan.


=========================================================
ATURAN HASIL TOOL
=========================================================

18. return dari run() HANYA berarti operasi benar-benar berhasil.

19. Jika operasi gagal, WAJIB raise Exception
    atau RuntimeError.

SALAH:

try:
    ...
except Exception as e:
    return {
        "message": f"Error: {e}"
    }


BENAR:

try:
    ...
except Exception as e:
    raise RuntimeError(str(e))


20. Jangan menelan exception.

21. Jangan menggunakan:

except:
    pass


22. Jangan mengubah error menjadi pesan sukses.

23. Jangan mengembalikan pesan seperti:

- "Error: ..."
- "Failed ..."
- "Gagal ..."
- "Tidak berhasil ..."

sebagai return sukses.

24. Sebelum return sukses, pastikan tindakan utama memang
    benar-benar telah dilakukan.

25. Jika skill sedang diperbaiki, perbaiki PENYEBAB bug.

26. Jangan hanya menyembunyikan exception dengan try/except.

27. Jika tindakan secara logis tidak dapat dilakukan,
    raise RuntimeError dengan alasan yang jelas.

28. Exception adalah sinyal penting untuk sistem
    auto-recovery Pochi.


=========================================================
ATURAN WINDOWS
=========================================================

29. Jika skill mengontrol Windows, buat implementasi yang
    kompatibel dengan Windows.

30. Jangan menganggap suatu aplikasi, file, window,
    atau proses pasti tersedia.

31. Periksa keberadaan target jika memungkinkan.

32. Jika target tidak ditemukan, raise RuntimeError.

33. Untuk operasi yang membutuhkan waktu,
    gunakan timeout yang masuk akal.

34. Hindari infinite loop.

35. Jangan membuat thread/background process permanen
    kecuali kemampuan memang membutuhkannya.

36. Jangan mematikan proses sistem Windows secara sembarangan.


=========================================================
ATURAN SELF-PROGRAMMING
=========================================================

37. Skill tidak boleh mengedit core Pochi.

38. Skill tidak boleh menghapus folder skills.

39. Skill tidak boleh menghapus database memory.

40. Skill tidak boleh memodifikasi dirinya sendiri.

41. Perubahan skill dilakukan oleh skill_builder /
    repair_skill, bukan oleh skill itu sendiri.

42. Jangan membuat mekanisme yang melewati ToolRegistry.

43. Jangan membuat subprocess shell bebas jika ada cara
    yang lebih aman dan spesifik.

44. Jika menggunakan subprocess, gunakan argument list
    jika memungkinkan, bukan shell=True.


=========================================================
KUALITAS
=========================================================

45. Source code harus lengkap dan langsung dapat digunakan.

46. Jangan beri placeholder seperti:
    pass
    TODO
    implement later

47. Jangan mengarang module/library yang tidak nyata.

48. Jangan memberi penjelasan di luar source code.

49. Jangan menghasilkan lebih dari satu TOOL.

50. TOOL["run"] wajib menunjuk ke function run.
"""


# =========================================================
# NAME
# =========================================================

def safe_filename(name):
    name = str(
        name or ""
    ).lower().strip()

    name = re.sub(
        r"[^a-z0-9_]+",
        "_",
        name
    )

    name = re.sub(
        r"_+",
        "_",
        name
    )

    name = name.strip("_")

    if not name:
        raise ValueError(
            "Nama skill tidak valid."
        )

    if name[0].isdigit():
        name = (
            "skill_" + name
        )

    return name


# =========================================================
# CLEAN GENERATED CODE
# =========================================================

def extract_code(raw):
    raw = str(
        raw or ""
    ).strip()

    if raw.startswith("```"):

        lines = raw.splitlines()

        if lines:
            lines = lines[1:]

        if (
            lines
            and
            lines[-1].strip() == "```"
        ):
            lines = lines[:-1]

        raw = "\n".join(
            lines
        )

    # Kalau model menulis "python" setelah ```
    if raw.lower().startswith(
        "python\n"
    ):
        raw = raw[7:]

    return raw.strip()


# =========================================================
# SAFE MODULE LEVEL CHECK
# =========================================================

def is_safe_constant_assignment(node):
    """
    Mengizinkan constant sederhana seperti:

    TIMEOUT = 5
    DEFAULT_NAME = "abc"

    tetapi tidak:

    X = os.system(...)
    """

    if not isinstance(
        node,
        ast.Assign
    ):
        return False

    for target in node.targets:

        if not isinstance(
            target,
            ast.Name
        ):
            return False

        if target.id == "TOOL":
            return True

    try:
        ast.literal_eval(
            node.value
        )

        return True

    except Exception:
        return False


# =========================================================
# SOURCE INSPECTION
# =========================================================

def inspect_source(code):
    try:

        tree = ast.parse(
            code
        )

    except SyntaxError as error:

        return False, (
            f"Syntax error baris "
            f"{error.lineno}: "
            f"{error.msg}"
        )

    has_run = False
    has_tool = False

    for node in tree.body:

        # ---------------------------------------------
        # IMPORT
        # ---------------------------------------------

        if isinstance(
            node,
            (
                ast.Import,
                ast.ImportFrom
            )
        ):
            continue

        # ---------------------------------------------
        # FUNCTION
        # ---------------------------------------------

        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef
            )
        ):

            if node.name == "run":
                has_run = True

            continue

        # ---------------------------------------------
        # CONSTANT / TOOL
        # ---------------------------------------------

        if isinstance(
            node,
            ast.Assign
        ):

            if not is_safe_constant_assignment(
                node
            ):

                return False, (
                    "Ada assignment tingkat module "
                    "yang dapat menjalankan kode saat import."
                )

            for target in node.targets:

                if (
                    isinstance(
                        target,
                        ast.Name
                    )
                    and
                    target.id == "TOOL"
                ):
                    has_tool = True

            continue

        # ---------------------------------------------
        # MODULE DOCSTRING
        # ---------------------------------------------

        if (
            isinstance(
                node,
                ast.Expr
            )
            and
            isinstance(
                node.value,
                ast.Constant
            )
            and
            isinstance(
                node.value.value,
                str
            )
        ):
            continue

        # ---------------------------------------------
        # TOLAK TOP-LEVEL EXECUTION
        # ---------------------------------------------

        return False, (
            "Skill memiliki kode yang berjalan "
            "langsung saat module di-import."
        )

    if not has_run:

        return False, (
            "Fungsi run() tidak ditemukan."
        )

    if not has_tool:

        return False, (
            "TOOL tidak ditemukan."
        )

    return True, "valid"


# =========================================================
# TOOL METADATA
# =========================================================

def get_tool_metadata(code):
    try:

        tree = ast.parse(
            code
        )

    except SyntaxError:
        return None

    for node in tree.body:

        if not isinstance(
            node,
            ast.Assign
        ):
            continue

        is_tool = any(
            isinstance(
                target,
                ast.Name
            )
            and
            target.id == "TOOL"
            for target in node.targets
        )

        if not is_tool:
            continue

        if not isinstance(
            node.value,
            ast.Dict
        ):
            return None

        metadata = {}

        has_run_reference = False

        for key_node, value_node in zip(
            node.value.keys,
            node.value.values
        ):

            try:

                key = ast.literal_eval(
                    key_node
                )

            except Exception:
                continue

            # TOOL["run"] harus menunjuk ke run
            if key == "run":

                if (
                    isinstance(
                        value_node,
                        ast.Name
                    )
                    and
                    value_node.id == "run"
                ):
                    has_run_reference = True

                continue

            try:

                metadata[key] = (
                    ast.literal_eval(
                        value_node
                    )
                )

            except Exception:

                return None

        metadata[
            "_has_run_reference"
        ] = has_run_reference

        return metadata

    return None


# =========================================================
# METADATA VALIDATION
# =========================================================

def validate_metadata(
    metadata,
    requested_name=None
):
    if not isinstance(
        metadata,
        dict
    ):

        return False, (
            "Metadata TOOL tidak valid."
        )

    required = {
        "name",
        "description",
        "parameters"
    }

    if not required.issubset(
        metadata.keys()
    ):

        return False, (
            "Metadata TOOL tidak lengkap."
        )

    if not metadata.get(
        "_has_run_reference"
    ):

        return False, (
            'TOOL["run"] harus menunjuk '
            "ke function run."
        )

    try:

        tool_name = safe_filename(
            metadata["name"]
        )

    except Exception as error:

        return False, str(
            error
        )

    if requested_name:

        expected = safe_filename(
            requested_name
        )

        if tool_name != expected:

            return False, (
                f"Nama TOOL harus "
                f"'{expected}', bukan "
                f"'{tool_name}'."
            )

    description = metadata.get(
        "description"
    )

    if not isinstance(
        description,
        str
    ) or not description.strip():

        return False, (
            "Description TOOL kosong."
        )

    parameters = metadata.get(
        "parameters"
    )

    if not isinstance(
        parameters,
        dict
    ):

        return False, (
            "parameters TOOL harus dictionary."
        )

    return True, "valid"


# =========================================================
# GENERATE SOURCE
# =========================================================

def generate_source(
    goal,
    requested_name=None,
    previous_error=None
):
    name_instruction = ""

    if requested_name:

        requested_name = safe_filename(
            requested_name
        )

        name_instruction = (
            "\n"
            f"Nama TOOL WAJIB: "
            f"{requested_name}\n"
        )

    repair_instruction = ""

    if previous_error:

        repair_instruction = f"""

HASIL GENERASI SEBELUMNYA DITOLAK VALIDATOR.

ALASAN:
{previous_error}

PERBAIKI MASALAH TERSEBUT.
Jangan ulangi kesalahan yang sama.
"""

    prompt = f"""
{GENERATOR_PROMPT}

=========================================================
KEMAMPUAN YANG DIMINTA
=========================================================

{goal}

{name_instruction}

{repair_instruction}

Buat source code skill sekarang.
"""

    response = generate_code(
        [
            {
                "role": "system",
                "content": (
                    "Kamu adalah software engineer "
                    "Python untuk sistem plugin Pochi. "
                    "Output hanya source code."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    raw = response[
        "message"
    ][
        "content"
    ]

    return extract_code(
        raw
    )


# =========================================================
# BACKUP
# =========================================================

def backup_existing(path):
    if not os.path.exists(
        path
    ):
        return None

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    filename = os.path.basename(
        path
    )

    base_name = os.path.splitext(
        filename
    )[0]

    backup_name = (
        f"{base_name}_"
        f"{stamp}.py"
    )

    backup_path = os.path.join(
        VERSIONS_DIR,
        backup_name
    )

    shutil.copy2(
        path,
        backup_path
    )

    return backup_path


# =========================================================
# FINAL COMPILE VALIDATION
# =========================================================

def validate_written_file(
    path
):
    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:

            source = file.read()

        compile(
            source,
            path,
            "exec"
        )

        return True, "valid"

    except Exception as error:

        return False, str(
            error
        )


# =========================================================
# BUILD SKILL
# =========================================================

def build_skill(
    goal,
    requested_name=None
):
    goal = str(
        goal or ""
    ).strip()

    if not goal:

        return {
            "success": False,
            "error": (
                "Tujuan skill kosong."
            )
        }

    if requested_name:

        requested_name = safe_filename(
            requested_name
        )

    previous_error = None
    code = None
    metadata = None

    # =====================================================
    # GENERATE + AUTO RETRY
    # =====================================================

    for attempt in range(
        1,
        MAX_GENERATION_ATTEMPTS + 1
    ):

        print(
            f"[SKILL BUILDER] "
            f"Generate attempt "
            f"{attempt}/"
            f"{MAX_GENERATION_ATTEMPTS}"
        )

        try:

            code = generate_source(
                goal=goal,
                requested_name=requested_name,
                previous_error=previous_error
            )

        except Exception as error:

            previous_error = (
                f"LLM generation error: "
                f"{error}"
            )

            print(
                "[SKILL BUILDER]",
                previous_error
            )

            continue

        # ---------------------------------------------
        # SOURCE CHECK
        # ---------------------------------------------

        valid, reason = inspect_source(
            code
        )

        if not valid:

            previous_error = reason

            print(
                f"[SKILL BUILDER] "
                f"Source ditolak: "
                f"{reason}"
            )

            continue

        # ---------------------------------------------
        # METADATA
        # ---------------------------------------------

        metadata = get_tool_metadata(
            code
        )

        valid, reason = validate_metadata(
            metadata,
            requested_name
        )

        if not valid:

            previous_error = reason

            print(
                f"[SKILL BUILDER] "
                f"Metadata ditolak: "
                f"{reason}"
            )

            continue

        # Valid.
        previous_error = None

        break

    # =====================================================
    # SEMUA ATTEMPT GAGAL
    # =====================================================

    if previous_error:

        return {
            "success": False,
            "error": (
                "Skill gagal dibuat setelah "
                f"{MAX_GENERATION_ATTEMPTS} "
                f"percobaan. "
                f"Error terakhir: "
                f"{previous_error}"
            ),
            "code": code
        }

    # =====================================================
    # TOOL NAME
    # =====================================================

    tool_name = safe_filename(
        metadata["name"]
    )

    if requested_name:

        tool_name = requested_name

    path = os.path.join(
        SKILLS_DIR,
        f"{tool_name}.py"
    )

    temp_path = (
        path + ".new"
    )

    # =====================================================
    # WRITE TEMP FIRST
    # =====================================================

    try:

        with open(
            temp_path,
            "w",
            encoding="utf-8"
        ) as file:

            file.write(
                code
            )

            if not code.endswith(
                "\n"
            ):
                file.write(
                    "\n"
                )

    except Exception as error:

        return {
            "success": False,
            "error": (
                f"Gagal menulis temporary skill: "
                f"{error}"
            )
        }

    # =====================================================
    # FINAL COMPILE
    # =====================================================

    valid, reason = validate_written_file(
        temp_path
    )

    if not valid:

        try:
            os.remove(
                temp_path
            )
        except OSError:
            pass

        return {
            "success": False,
            "error": (
                f"Validasi akhir gagal: "
                f"{reason}"
            )
        }

    # =====================================================
    # BACKUP OLD VERSION
    # =====================================================

    try:

        backup = backup_existing(
            path
        )

    except Exception as error:

        try:
            os.remove(
                temp_path
            )
        except OSError:
            pass

        return {
            "success": False,
            "error": (
                f"Gagal membuat backup: "
                f"{error}"
            )
        }

    # =====================================================
    # INSTALL
    # =====================================================

    try:

        os.replace(
            temp_path,
            path
        )

    except Exception as error:

        try:
            os.remove(
                temp_path
            )
        except OSError:
            pass

        return {
            "success": False,
            "error": (
                f"Gagal memasang skill: "
                f"{error}"
            )
        }

    print(
        f"[SKILL BUILDER] "
        f"Skill '{tool_name}' "
        f"berhasil dipasang."
    )

    # =====================================================
    # RESULT
    # =====================================================

    return {
        "success": True,
        "name": tool_name,
        "path": path,
        "backup": backup,
        "description": metadata.get(
            "description",
            ""
        )
    }