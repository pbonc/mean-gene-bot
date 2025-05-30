import os
import re

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
GIF_EXTS = {".gif"}
VIDEO_EXTS = {".mp4", ".webm"}

def get_media_files(base_dir):
    mapping = {}

    gifs_dir = os.path.join(base_dir, "gifs")
    heart_dir = os.path.join(gifs_dir, "heart")

    # 1. Standard gifs/images in gifs/
    if os.path.isdir(gifs_dir):
        for fname in os.listdir(gifs_dir):
            fpath = os.path.join(gifs_dir, fname)
            rel_path = os.path.relpath(fpath, base_dir).replace("\\", "/")
            ext = os.path.splitext(fname)[1].lower()
            command = os.path.splitext(fname)[0].lower()
            if os.path.isfile(fpath) and (ext in IMAGE_EXTS or ext in GIF_EXTS or ext in VIDEO_EXTS):
                is_gif = ext in GIF_EXTS
                duration = 3 if is_gif else 5
                mapping[f"!{command}"] = (rel_path, duration, is_gif)

    # 2. Heart gifs/images in gifs/heart/
    if os.path.isdir(heart_dir):
        for fname in os.listdir(heart_dir):
            fpath = os.path.join(heart_dir, fname)
            rel_path = os.path.relpath(fpath, base_dir).replace("\\", "/")
            ext = os.path.splitext(fname)[1].lower()
            base = os.path.splitext(fname)[0].lower()  # e.g. dar, dar2, hop
            if os.path.isfile(fpath) and (ext in IMAGE_EXTS or ext in GIF_EXTS or ext in VIDEO_EXTS):
                is_gif = ext in GIF_EXTS
                duration = 3 if is_gif else 5
                m = re.match(r"([a-z]+)(\d*)$", base)
                if m:
                    name = m.group(1)   # e.g. "dar"
                    num = m.group(2)    # e.g. "", "2", etc.
                    cmd = f"!{name}<3{num}"
                    mapping[cmd] = (rel_path, duration, is_gif)
    return mapping

if __name__ == "__main__":
    # For dev test: print the mapping
    base_dir = os.path.dirname(__file__)
    mapping = get_media_files(base_dir=os.path.join(base_dir, "../overlay"))
    for cmd, (rel, dur, gif) in mapping.items():
        print(f"{cmd:15} -> {rel} ({dur}s) gif={gif}")