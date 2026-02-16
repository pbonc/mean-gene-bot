import pygame
import time

pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=1024)
pygame.init()

print("Testing SFX playback with pygame...")
try:
    sound = pygame.mixer.Sound(r"assets/sfx/ruse.wav")
    sound.set_volume(0.6)
    channel = sound.play()
    print("Sound play triggered. Waiting for playback to finish...")
    while channel.get_busy():
        pygame.time.wait(10)
    print("Playback finished.")
except Exception as e:
    print(f"Error playing SFX: {e}")
finally:
    pygame.quit()
