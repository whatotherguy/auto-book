import shutil
from pathlib import Path
from ..config import settings


def project_root(project_id: int) -> Path:
    return settings.data_root / str(project_id)


def chapter_root(project_id: int, chapter_number: int) -> Path:
    return project_root(project_id) / "chapters" / f"{chapter_number:02d}"


def ensure_chapter_dirs(project_id: int, chapter_number: int) -> dict[str, Path]:
    root = chapter_root(project_id, chapter_number)
    paths = {
        "root": root,
        "source": root / "source",
        "working": root / "working",
        "analysis": root / "analysis",
        "exports": root / "exports",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def clear_directory(path: Path) -> None:
    if not path.exists():
        return

    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def delete_chapter_dirs(project_id: int, chapter_number: int) -> None:
    root = chapter_root(project_id, chapter_number)
    if root.exists():
        shutil.rmtree(root)


def delete_project_dirs(project_id: int) -> None:
    root = project_root(project_id)
    if root.exists():
        shutil.rmtree(root)
