from pathlib import Path
from .constants import VALID_EXTENSIONS

def scan_music(music_dir: str) -> dict:
    categories = {}
    music_path = Path(music_dir)
    if not music_path.exists():
        return categories
    for f in music_path.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in VALID_EXTENSIONS:
            continue
        relative = f.relative_to(music_path)
        parts = relative.parts
        category = parts[0] if len(parts) > 1 else "Raiz (Musica suelta)"
        if category not in categories:
            categories[category] = []
        categories[category].append(str(f))
    return categories
