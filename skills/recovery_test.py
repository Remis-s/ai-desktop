def run(a: float = 10, b: float = 2):
    try:
        if b == 0:
            raise RuntimeError("Pembagian dengan nol tidak diizinkan")
        result = a / b
    except Exception as e:
        raise RuntimeError(str(e))

    return {
        "message": f"{a} dibagi {b} = {result}",
        "result": result
    }


TOOL = {
    "name": "recovery_test",
    "description": (
        "Membagi angka a dengan angka b dan mengembalikan hasil pembagian. "
        "Skill ini digunakan untuk menguji apakah sistem auto-recovery "
        "dapat menemukan dan memperbaiki bug implementasi."
    ),
    "parameters": {
        "a": {
            "type": "number",
            "description": "Angka yang akan dibagi"
        },
        "b": {
            "type": "number",
            "description": "Angka pembagi"
        }
    },
    "run": run
}
