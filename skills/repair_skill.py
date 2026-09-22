import os

from skill_builder import build_skill
from tool_registry import registry


BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

SKILLS_DIR = os.path.join(
    BASE_DIR,
    "skills"
)


def run(
    skill_name: str,
    problem: str,
    desired_behavior: str = ""
):
    skill_name = str(
        skill_name or ""
    ).strip()

    problem = str(
        problem or ""
    ).strip()

    desired_behavior = str(
        desired_behavior or ""
    ).strip()

    if not skill_name:
        raise ValueError(
            "Nama skill yang mau diperbaiki kosong."
        )

    if not problem:
        raise ValueError(
            "Masalah skill belum dijelaskan."
        )

    skill_path = os.path.join(
        SKILLS_DIR,
        f"{skill_name}.py"
    )

    if not os.path.isfile(skill_path):
        raise RuntimeError(
            f"Skill '{skill_name}' tidak ditemukan."
        )

    with open(
        skill_path,
        "r",
        encoding="utf-8"
    ) as file:
        old_code = file.read()

    goal = f"""
Perbaiki skill Python bernama "{skill_name}".

MASALAH:
{problem}

PERILAKU YANG DIINGINKAN:
{desired_behavior or "Pertahankan fungsi awal skill tetapi perbaiki masalahnya."}

SOURCE CODE SAAT INI:

{old_code}

Buat ulang skill yang lebih robust.

PENTING:
- Pertahankan nama TOOL: {skill_name}
- Pertahankan tujuan utama skill
- Perbaiki penyebab masalah
- Jangan mengubah file lain
- Jangan menghapus kemampuan yang masih berfungsi
- Buat parameter tetap generik dan reusable
"""

    result = build_skill(
        goal=goal,
        requested_name=skill_name
    )

    if not result.get("success"):
        raise RuntimeError(
            result.get(
                "error",
                "Perbaikan skill gagal."
            )
        )

    registry.reload()

    return {
        "message": (
            f"Skill '{skill_name}' berhasil diperbaiki "
            f"dan versi barunya sudah dimuat."
        ),
        "skill_name": skill_name,
        "backup": result.get("backup"),
        "path": result.get("path")
    }


TOOL = {
    "name": "repair_skill",

    "description": (
        "Memperbaiki skill Pochi yang sudah ada ketika skill "
        "mengalami error, tidak bekerja sesuai tujuan, atau perlu "
        "ditingkatkan. Versi sebelumnya akan dibackup."
    ),

    "parameters": {
        "skill_name": {
            "type": "string",
            "description": (
                "Nama skill yang perlu diperbaiki, "
                "contoh: mouse_movement"
            )
        },

        "problem": {
            "type": "string",
            "description": (
                "Masalah atau error yang terjadi pada skill."
            )
        },

        "desired_behavior": {
            "type": "string",
            "description": (
                "Perilaku yang seharusnya dilakukan setelah diperbaiki."
            )
        }
    },

    "run": run
}