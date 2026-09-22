def run():
    try:
        result = 10 / 0
    except ZeroDivisionError:
        return {
            "message": "Error: Division by zero is not allowed."
        }
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
