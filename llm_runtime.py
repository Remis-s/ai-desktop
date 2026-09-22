import ollama


MODEL = "qwen3:8b"


def fast_json(messages, num_predict=300):
    """
    Untuk:
    - klasifikasi
    - diagnosis
    - keputusan sederhana
    - output JSON

    Tidak memakai thinking panjang.
    """

    return ollama.chat(
        model=MODEL,
        messages=messages,
        format="json",
        think=False,
        options={
            "temperature": 0.0,
            "num_predict": num_predict
        }
    )


def agent_json(messages):
    """
    Untuk planner/tool calling Pochi.
    """

    return ollama.chat(
        model=MODEL,
        messages=messages,
        format="json",
        think=False,
        options={
            "temperature": 0.15,
            "num_predict": 700
        }
    )


def generate_code(messages):
    """
    Untuk membuat / memperbaiki skill.

    Tetap diberi output lebih panjang,
    tapi thinking panjang dimatikan agar
    tidak makan waktu bermenit-menit.
    """

    print(
        "[LLM CODE] Mulai generate..."
    )

    response = ollama.chat(
        model=MODEL,
        messages=messages,
        think=False,
        options={
            "temperature": 0.15,
            "num_predict": 1600
        }
    )

    print(
        "[LLM CODE] Generate selesai."
    )

    return response