import asyncio
import edge_tts

async def main():
    text = "Halo. Saya siap membantu."
    voice = "id-ID-GadisNeural"

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save("response.mp3")

asyncio.run(main())