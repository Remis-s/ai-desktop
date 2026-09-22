def run():
    # Sengaja rusak untuk menguji auto-recovery.
    result = 10 / 0

    return {
        "message": f"Recovery test berhasil: {result}"
    }


TOOL = {
    "name": "recovery_test",

    "description": (
        "Skill khusus untuk menguji kemampuan Pochi "
        "mendeteksi dan memperbaiki bug pada skill."
    ),

    "parameters": {},

    "run": run
}