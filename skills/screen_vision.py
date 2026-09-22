from vision_runtime import analyze_latest_screen


def run(instruction: str = ""):
    instruction = str(
        instruction or ""
    ).strip()

    user_instruction = instruction

    vision_prompt = f"""
Kamu adalah sistem penglihatan desktop Windows untuk Pochi.

Analisis SELURUH screenshot dari kiri atas sampai kanan bawah.

JANGAN hanya membaca teks yang paling besar atau paling jelas.
JANGAN hanya fokus pada Command Prompt / terminal.

Tugas utama:
1. Kenali semua window/aplikasi yang benar-benar terlihat.
2. Jelaskan tata letak layar secara keseluruhan.
3. Sebutkan window yang berada di depan jika terlihat.
4. Sebutkan elemen UI penting yang terlihat.
5. Sebutkan teks penting hanya jika memang relevan.
6. Jangan menyalin seluruh isi terminal/log.
7. Jangan mengarang aplikasi atau elemen yang tidak terlihat.
8. Jika suatu hal tidak yakin, tandai sebagai tidak yakin.

Bedakan:
- teks yang terlihat
- aplikasi/window
- tombol/menu/icon
- posisi visual

Gunakan posisi seperti:
- kiri atas
- tengah atas
- kanan atas
- kiri
- tengah
- kanan
- kiri bawah
- tengah bawah
- kanan bawah

PERMINTAAN USER:
{user_instruction}

Jawab dalam Bahasa Indonesia.

Format jawaban:

RINGKASAN:
<gambaran umum layar>

WINDOW/APLIKASI TERLIHAT:
- <nama / deskripsi> — <posisi>
- ...

ELEMEN PENTING:
- <elemen> — <posisi>
- ...

TEKS PENTING:
- <teks yang relevan saja>

KESIMPULAN:
<jawaban langsung terhadap permintaan user>
""".strip()

    result = analyze_latest_screen(
        vision_prompt
    )

    return {
        "message": (
            "Screenshot berhasil dianalisis "
            "menggunakan vision."
        ),

        "path": result["path"],

        "analysis": result["analysis"]
    }


TOOL = {
    "name": "screen_vision",

    "description": (
        "Melihat dan memahami screenshot desktop terbaru "
        "menggunakan model vision. "
        "Gunakan untuk memahami isi visual layar, aplikasi, "
        "window, tombol, menu, ikon, teks, dialog, dan layout. "
        "Untuk keadaan layar saat ini, gunakan screen_capture "
        "terlebih dahulu agar gambar tidak basi."
    ),

    "parameters": {
        "instruction": {
            "type": "string",
            "description": (
                "Hal yang ingin diketahui dari screenshot. "
                "Contoh: 'Ceritakan seluruh isi layar', "
                "'Cari tombol Save', atau "
                "'Apa yang sedang terbuka di desktop?'."
            )
        }
    },

    "run": run
}