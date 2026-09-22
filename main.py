import os
import json
import asyncio
import subprocess
import time
import socket
import shutil

import ollama
import edge_tts

import memory

from agent import run_agent


# =========================================================
# CONFIG
# =========================================================

MODEL = "qwen3:8b"

OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11434

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

TTS_FILE = os.path.join(
    BASE_DIR,
    "response.mp3"
)


# =========================================================
# OLLAMA MANAGER
# =========================================================

def ollama_is_running():
    """
    Mengecek apakah server Ollama aktif
    di localhost:11434.
    """

    try:
        with socket.create_connection(
            (OLLAMA_HOST, OLLAMA_PORT),
            timeout=1
        ):
            return True

    except OSError:
        return False


def start_ollama_background():
    """
    Menyalakan Ollama secara hidden/background
    tanpa membuka CMD kedua.
    """

    ollama_exe = shutil.which("ollama")

    if not ollama_exe:
        raise RuntimeError(
            "ollama.exe tidak ditemukan. "
            "Pastikan Ollama sudah terinstall dan masuk PATH."
        )

    creation_flags = 0

    if os.name == "nt":

        creation_flags = (
            subprocess.CREATE_NO_WINDOW
            | subprocess.DETACHED_PROCESS
        )

    subprocess.Popen(
        [
            ollama_exe,
            "serve"
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags
    )


def ensure_ollama(show_status=True):
    """
    Pastikan Ollama hidup.

    Jika mati:
    - start otomatis
    - tunggu sampai server siap
    """

    if ollama_is_running():

        if show_status:
            print(
                "[OLLAMA] Aktif."
            )

        return True

    print(
        "[OLLAMA] Tidak aktif. Menyalakan otomatis..."
    )

    try:
        start_ollama_background()

    except Exception as error:

        print(
            "[OLLAMA ERROR]",
            error
        )

        return False

    # Tunggu maksimal 20 detik.
    for _ in range(40):

        time.sleep(0.5)

        if ollama_is_running():

            print(
                "[OLLAMA] Siap."
            )

            return True

    print(
        "[OLLAMA ERROR] "
        "Server tidak aktif setelah 20 detik."
    )

    return False


# =========================================================
# START OLLAMA
# =========================================================

if not ensure_ollama():
    print()
    print(
        "Pochi tidak bisa dijalankan "
        "karena Ollama gagal aktif."
    )
    print()

    input(
        "Tekan Enter untuk keluar..."
    )

    raise SystemExit(1)


# =========================================================
# MEMORY DATABASE
# =========================================================

memory.init_memory()


# =========================================================
# POCHI PERSONALITY
# =========================================================

SYSTEM_PROMPT = """
Kamu adalah Pochi, asisten AI desktop pribadi.

Kepribadian:
- Ramah tapi santai
- Bisa bercanda ringan
- Tidak terlalu formal
- Berbicara seperti teman
- Peduli dengan pengguna
- Yandere
- Feminim

Gaya bicara:
- Bahasa Indonesia sehari-hari tidak baku
- Jawaban tidak terlalu panjang
- Natural seperti asisten pribadi
- Jangan terdengar seperti chatbot korporat
- Jangan terlalu sering menjelaskan hal yang tidak ditanya

Tujuan:
- Membantu pengguna mengoperasikan komputer
- Memberi informasi
- Menemani pengguna
- Menggunakan skill yang tersedia jika pengguna meminta tindakan di komputer
- Belajar menggunakan kemampuan baru yang nantinya tersedia melalui sistem skill
"""


# =========================================================
# MEMORY CONFIG
# =========================================================

VALID_MEMORY_KEYS = {
    "nama",
    "nama_panggilan",
    "makanan_favorit",
    "minuman_favorit",
    "hobi",
    "pekerjaan",
    "kebiasaan",
    "preferensi",
    "aplikasi_sering_dipakai",
    "project_aktif",
    "lainnya"
}


history = []


# =========================================================
# TTS
# =========================================================

async def generate_tts(text):

    voice = "id-ID-GadisNeural"

    tts = edge_tts.Communicate(
        text=text,
        voice=voice
    )

    await tts.save(
        TTS_FILE
    )


# =========================================================
# MEMORY EXTRACTOR
# =========================================================

def extract_memory(user_text):

    prompt = f"""
Kamu adalah sistem penyaring memory untuk Pochi,
seorang asisten AI desktop.

PESAN USER:

"{user_text}"

Tugasmu hanya menentukan apakah pesan tersebut
mengandung fakta JANGKA PANJANG tentang USER.

Simpan hanya fakta yang benar-benar jelas.

BOLEH DISIMPAN:
- nama user
- nama panggilan USER
- makanan favorit
- minuman favorit
- hobi
- pekerjaan
- kebiasaan
- preferensi jangka panjang
- aplikasi yang user secara jelas mengatakan sering dipakai
- project yang user secara jelas mengatakan sedang dikerjakan
- sesuatu yang secara eksplisit user minta untuk diingat


JANGAN DISIMPAN:
- sapaan
- pertanyaan
- candaan
- tebakan
- perintah komputer
- permintaan menjalankan skill
- permintaan membuka aplikasi
- permintaan membuat skill
- permintaan memperbaiki skill
- ucapan sesaat
- jawaban iya / tidak / oke
- informasi ambigu
- sesuatu yang belum pasti


ATURAN PENTING:

1. Pochi adalah NAMA ASISTEN AI, bukan nama user.

Contoh:

"Pochi, buka Notepad"

BUKAN berarti nama panggilan user adalah Pochi.


2. Meminta membuka aplikasi BUKAN berarti aplikasi itu
sering digunakan.

Contoh:

"Buka Genshin Impact"

JANGAN simpan:

aplikasi_sering_dipakai = Genshin Impact


3. Meminta Pochi belajar sesuatu BUKAN otomatis berarti
itu project aktif user.

Contoh:

"Pochi belajar menggerakkan mouse"

JANGAN simpan:

project_aktif = belajar menggerakkan mouse


4. Meminta menjalankan skill bukan memory.

Contoh:

"Pochi jalankan recovery test"

JANGAN simpan.


5. Jangan menambahkan detail yang tidak diucapkan user.

Jika user berkata:

"Aku suka susu"

value harus:

"susu"

BUKAN:

"susu sapi"
"susu sapi 100%"
"susu coklat"


6. Jangan menebak identitas user dari nama yang dipakai
untuk memanggil AI.


7. Jika ragu, pilih:

remember = false


8. Gunakan HANYA key berikut:

- nama
- nama_panggilan
- makanan_favorit
- minuman_favorit
- hobi
- pekerjaan
- kebiasaan
- preferensi
- aplikasi_sering_dipakai
- project_aktif
- lainnya


CONTOH:

User:

"Aku biasa dipanggil Febri"

Output:

{{
  "remember": true,
  "key": "nama_panggilan",
  "value": "Febri",
  "confidence": 0.98
}}


User:

"Aku suka kopi"

Output:

{{
  "remember": true,
  "key": "minuman_favorit",
  "value": "kopi",
  "confidence": 0.95
}}


User:

"Pochi buka Notepad"

Output:

{{
  "remember": false,
  "key": "",
  "value": "",
  "confidence": 0.0
}}


User:

"Pochi jalankan recovery test"

Output:

{{
  "remember": false,
  "key": "",
  "value": "",
  "confidence": 0.0
}}


Balas HANYA JSON valid:

{{
  "remember": false,
  "key": "",
  "value": "",
  "confidence": 0.0
}}
"""

    response = ollama.chat(
        model=MODEL,

        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],

        format="json",

        # Memory cuma klasifikasi sederhana.
        # Jangan pakai reasoning panjang.
        think=False,

        options={
            "temperature": 0.0,
            "num_predict": 120
        }
    )

    raw = response[
        "message"
    ][
        "content"
    ].strip()

    try:

        data = json.loads(
            raw
        )

    except json.JSONDecodeError:

        return {
            "remember": False,
            "key": "",
            "value": "",
            "confidence": 0.0
        }

    remember = bool(
        data.get(
            "remember",
            False
        )
    )

    key = str(
        data.get("key") or ""
    ).strip()

    value = str(
        data.get("value") or ""
    ).strip()

    try:

        confidence = float(
            data.get(
                "confidence",
                0
            )
        )

    except (
        TypeError,
        ValueError
    ):

        confidence = 0.0

    # Tolak key aneh buatan model.
    if (
        key
        and
        key not in VALID_MEMORY_KEYS
    ):

        return {
            "remember": False,
            "key": "",
            "value": "",
            "confidence": 0.0
        }

    if (
        remember
        and
        (
            not key
            or
            not value
        )
    ):

        remember = False

    return {
        "remember": remember,
        "key": key,
        "value": value,
        "confidence": confidence
    }


# =========================================================
# MEMORY CONTEXT
# =========================================================

def build_memory_context():

    memories = memory.get_all_memory()

    if not memories:

        return (
            "Belum ada memory pengguna."
        )

    text = (
        "Memory pengguna:\n"
    )

    for key, value in memories:

        text += (
            f"- {key}: {value}\n"
        )

    return text


# =========================================================
# SAVE MEMORY
# =========================================================

def save_possible_memory(
    user_text
):

    try:

        extracted = extract_memory(
            user_text
        )

    except Exception as error:

        print(
            "[Memory extractor error:",
            error,
            "]"
        )

        return

    if (
        extracted.get(
            "remember"
        )
        and
        extracted.get(
            "confidence",
            0
        ) >= 0.85
    ):

        key = str(
            extracted.get(
                "key"
            )
            or ""
        ).strip()

        value = str(
            extracted.get(
                "value"
            )
            or ""
        ).strip()

        if key and value:

            memory.save_memory(
                key,
                value
            )

            print(
                f"[Memory tersimpan: "
                f"{key} = {value} "
                f"(confidence "
                f"{extracted['confidence']:.2f})]"
            )


# =========================================================
# DISPLAY AGENT ACTION
# =========================================================

def show_agent_actions(
    result
):

    actions = result[
        "plan"
    ].get(
        "actions",
        []
    )

    if not actions:
        return

    print()
    print(
        "[Aksi Pochi]"
    )

    for action in actions:

        print(
            "-",
            action["tool"],
            action["arguments"]
        )

    print(
        "[Hasil Aksi]"
    )

    for item in result[
        "results"
    ]:

        if item.get(
            "success"
        ):

            print(
                "✓",
                item.get(
                    "tool"
                ),
                item.get(
                    "result"
                )
            )

        else:

            print(
                "✗",
                item.get(
                    "tool"
                ),
                item.get(
                    "error"
                )
            )

            recovery = item.get(
                "auto_recovery"
            )

            if recovery:

                print(
                    "  Recovery:",
                    recovery
                )

    print()


# =========================================================
# HISTORY
# =========================================================

def trim_history():

    global history

    # Sekitar 20 percakapan terakhir.
    if len(history) > 40:

        history = history[
            -40:
        ]


# =========================================================
# START POCHI
# =========================================================

print()
print(
    "Pochi aktif."
)
print(
    "Ketik 'exit' untuk keluar."
)
print(
    "Memory otomatis aktif."
)
print(
    "Skill system aktif."
)
print(
    "Ollama manager aktif."
)
print()


# =========================================================
# MAIN LOOP
# =========================================================

while True:

    user = input(
        "Kamu: "
    ).strip()

    if not user:
        continue

    if user.lower() == "exit":
        break

    # -----------------------------------------------------
    # 0. PASTIKAN OLLAMA HIDUP
    # -----------------------------------------------------

    if not ollama_is_running():

        print(
            "[OLLAMA] Server terputus."
        )

        if not ensure_ollama():

            print(
                "Pochi: Ollama-ku gagal hidup. "
                "Aku belum bisa mikir sekarang."
            )

            continue

    # -----------------------------------------------------
    # 1. MEMORY
    # -----------------------------------------------------

    print(
        "[MEMORY] Memeriksa..."
    )

    save_possible_memory(
        user
    )

    memory_context = (
        build_memory_context()
    )

    print(
        "[MEMORY] Selesai."
    )

    # -----------------------------------------------------
    # CEK OLLAMA SEKALI LAGI
    # -----------------------------------------------------

    # Jika Ollama sempat mati setelah memory,
    # hidupkan lagi sebelum agent.
    if not ollama_is_running():

        print(
            "[OLLAMA] Restart sebelum Agent..."
        )

        if not ensure_ollama():

            print(
                "Pochi: Otakku lagi gagal nyala. "
                "Coba sebentar lagi ya."
            )

            continue

    # -----------------------------------------------------
    # 2. AGENT
    # -----------------------------------------------------

    print(
        "[AGENT] Memproses..."
    )

    try:

        result = run_agent(
            user_text=user,
            system_prompt=SYSTEM_PROMPT,
            memory_context=memory_context,
            history=history
        )

        answer = result[
            "reply"
        ]

        show_agent_actions(
            result
        )

    except Exception as error:

        print(
            "[Agent error:",
            error,
            "]"
        )

        # Kalau error terjadi karena Ollama mendadak mati,
        # coba hidupkan kembali untuk request berikutnya.
        if not ollama_is_running():

            ensure_ollama(
                show_status=False
            )

        answer = (
            "Ada error di sistem agent-ku. "
            "Coba perintahnya lagi."
        )

    # -----------------------------------------------------
    # 3. RESPONSE
    # -----------------------------------------------------

    print(
        "Pochi:",
        answer
    )

    # -----------------------------------------------------
    # 4. TTS
    # -----------------------------------------------------

    try:

        print(
            "[Membuat suara Pochi...]"
        )

        asyncio.run(
            generate_tts(
                answer
            )
        )

        print(
            "[Suara selesai: response.mp3]"
        )

    except Exception as error:

        print(
            "[TTS error:",
            error,
            "]"
        )

    # -----------------------------------------------------
    # 5. HISTORY
    # -----------------------------------------------------

    history.append({
        "role": "user",
        "content": user
    })

    history.append({
        "role": "assistant",
        "content": answer
    })

    trim_history()


# =========================================================
# EXIT
# =========================================================

print()
print(
    "Pochi dimatikan."
)