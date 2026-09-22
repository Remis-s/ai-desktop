from skill_builder import build_skill
from tool_registry import registry


def run(goal: str, requested_name: str = ""):
    goal = str(goal or "").strip()
    requested_name = str(requested_name or "").strip()

    if not goal:
        raise ValueError(
            "Kemampuan yang ingin dibuat belum dijelaskan."
        )

    result = build_skill(
        goal=goal,
        requested_name=(
            requested_name
            if requested_name
            else None
        )
    )

    if not result.get("success"):
        raise RuntimeError(
            result.get(
                "error",
                "Gagal membuat skill."
            )
        )

    # Langsung kenalkan skill baru ke Pochi.
    registry.reload()

    skill_name = result.get(
        "name",
        "unknown"
    )

    description = result.get(
        "description",
        ""
    )

    return {
        "message": (
            f"Skill baru '{skill_name}' berhasil dibuat "
            f"dan sudah dimuat ke sistem."
        ),
        "skill_name": skill_name,
        "description": description,
        "path": result.get("path"),
        "backup": result.get("backup")
    }


TOOL = {
    "name": "create_skill",

    "description": (
        "Membuat kemampuan atau skill Python baru untuk Pochi "
        "ketika pengguna meminta Pochi belajar kemampuan yang "
        "belum tersedia. Gunakan ini untuk menambah kemampuan, "
        "bukan untuk menjalankan kemampuan yang sebenarnya sudah ada."
    ),

    "parameters": {
        "goal": {
            "type": "string",
            "description": (
                "Penjelasan lengkap dan generik tentang kemampuan "
                "baru yang harus dibuat."
            )
        },

        "requested_name": {
            "type": "string",
            "description": (
                "Nama skill snake_case jika nama tertentu diperlukan. "
                "Boleh dikosongkan agar sistem menentukan nama sendiri."
            )
        }
    },

    "run": run
}