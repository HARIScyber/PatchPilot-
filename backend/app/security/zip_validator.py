"""Safe zip extraction utility with path traversal and zip bomb defenses."""
from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import List

logger = logging.getLogger("patchpilot.security.zip")

# Max uncompressed size: default 50MB
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_FILE_COUNT = 1000
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200


class ZipSecurityError(Exception):
    """Raised when a zip archive violates security policies."""
    pass


def validate_and_extract_zip(
    zip_path: Path | str,
    target_dir: Path | str,
    max_size_bytes: int = MAX_UNCOMPRESSED_BYTES,
) -> List[str]:
    """Safely extract a zip archive to target_dir.

    Protections:
    - Path traversal: disallows '..' or drive absolute paths
    - Zip bomb: limits total uncompressed size and total file count
    - Symlinks: rejects symlinks pointing outside target_dir
    """
    zip_path = Path(zip_path).resolve()
    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    if not zipfile.is_zipfile(zip_path):
        raise ZipSecurityError("Provided file is not a valid zip archive.")

    extracted_files: List[str] = []
    total_size = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        infolist = zf.infolist()
        if len(infolist) > MAX_FILE_COUNT:
            raise ZipSecurityError(
                f"Zip contains {len(infolist)} entries, exceeding safety limit of {MAX_FILE_COUNT}."
            )

        for member in infolist:
            total_size += member.file_size
            if total_size > max_size_bytes:
                raise ZipSecurityError(
                    f"Uncompressed size exceeds maximum safety limit ({max_size_bytes // (1024 * 1024)} MB)."
                )

            # Prevent directory traversal attacks
            dest_path = (target_dir / member.filename).resolve()
            if not dest_path.is_relative_to(target_dir):
                raise ZipSecurityError(
                    f"Malicious zip entry detected (path traversal attempt): {member.filename}"
                )

            # Check for illegal symlinks
            if (member.external_attr >> 16) & 0o120000 == 0o120000:
                # Symlink entry - reject to prevent arbitrary symlink pointing
                raise ZipSecurityError(f"Symlinks are disallowed in uploaded archives: {member.filename}")
            if member.file_size > MAX_FILE_BYTES:
                raise ZipSecurityError(f"Zip entry exceeds per-file size limit: {member.filename}")
            if member.file_size and (member.compress_size == 0 or member.file_size / member.compress_size > MAX_COMPRESSION_RATIO):
                raise ZipSecurityError(f"Zip entry exceeds compression-ratio limit: {member.filename}")

        # If all checks pass, extract
        zf.extractall(target_dir)

        for member in infolist:
            if not member.is_dir():
                extracted_files.append(str((target_dir / member.filename).resolve()))

    logger.info("Successfully extracted %d files to %s (size: %d bytes)", len(extracted_files), target_dir, total_size)
    return extracted_files
