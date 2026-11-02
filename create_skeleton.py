import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Ensure required subdirectories exist
required_dirs = [
    BASE_DIR / "backend" / "app" / "api",
    BASE_DIR / "backend" / "app" / "core",
    BASE_DIR / "backend" / "app" / "models",
    BASE_DIR / "backend" / "app" / "schemas",
    BASE_DIR / "backend" / "app" / "services",
    BASE_DIR / "backend" / "app" / "security",
    BASE_DIR / "backend" / "app" / "database",
    BASE_DIR / "backend" / "tests",
    BASE_DIR / "frontend" / "src" / "components",
    BASE_DIR / "frontend" / "src" / "pages",
    BASE_DIR / "frontend" / "src" / "services",
    BASE_DIR / "frontend" / "src" / "hooks",
    BASE_DIR / "frontend" / "src" / "types",
    BASE_DIR / "training" / "data",
    BASE_DIR / "sample_projects",
    BASE_DIR / "docker",
    BASE_DIR / "docs"
]

for d in required_dirs:
    os.makedirs(d, exist_ok=True)

print("Project skeleton directories created.")
