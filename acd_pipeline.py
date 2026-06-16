"""ACD -> L5X -> exploded-tree conversion pipeline.

Drives the C# `l5xgit` CLI (built from `L5xCmd.sln`) to turn an uploaded Studio
5000 `.acd` file into the per-project cache layout the viewer browses:

    cache/{project}/
        {project}.acd          # copy of the imported ACD
        {project}.l5x          # intermediate conversion output
        exploded/              # tree root (exploded/RSLogix5000Content/...)

ACD->L5X conversion uses the Rockwell Logix Designer SDK, so this only works on
a host with Studio 5000 / the Logix Designer SDK installed.
"""

import hashlib
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.resolve()
CACHE_DIR = (REPO_ROOT / "cache").resolve()
SOLUTION = REPO_ROOT / "L5xCmd.sln"
EXE_PATH = REPO_ROOT / "artifacts" / "bin" / "Release" / "l5xgit.exe"

# Substring that flags a missing-dependency explode failure, so we can retry
# with --unsafe-skip-dependency-check (L5X exported without the Dependencies
# option lacks the AOI dependency info the safety check requires).
_DEP_ERROR_RE = re.compile(r"depend", re.IGNORECASE)


class PipelineError(RuntimeError):
    """Raised when any pipeline step fails, with a readable message."""


def _safe_project_name(filename: str) -> str:
    """Imported ACD filename without extension, sanitized for a folder name."""
    stem = Path(filename or "").stem.strip()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_")
    if not stem:
        raise PipelineError(f"Could not derive a project name from {filename!r}.")
    return stem


def l5xgit_exe() -> Path:
    """Return the path to l5xgit.exe, building the solution if it's missing."""
    if EXE_PATH.is_file():
        return EXE_PATH

    try:
        result = subprocess.run(
            ["dotnet", "build", str(SOLUTION), "-c", "Release"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise PipelineError(
            "dotnet SDK not found on PATH; cannot build l5xgit.exe."
        ) from exc

    if result.returncode != 0:
        raise PipelineError(
            "Failed to build l5xgit.exe via `dotnet build`:\n"
            f"{result.stdout}\n{result.stderr}".strip()
        )

    if not EXE_PATH.is_file():
        raise PipelineError(
            f"Build succeeded but l5xgit.exe not found at {EXE_PATH}."
        )
    return EXE_PATH


def _run(args: list[str]) -> subprocess.CompletedProcess:
    """Run an l5xgit subcommand, raising PipelineError on a non-zero exit."""
    proc = subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True)
    return proc


def _read_hash(hash_file: Path) -> str | None:
    """Return the stored ACD content hash, or None if absent/unreadable."""
    try:
        return hash_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def import_acd(acd_bytes: bytes, filename: str) -> str:
    """Convert uploaded ACD bytes into cache/{project}/exploded; return project.

    Steps: copy ACD -> `acd2l5x` -> `explode`. The explode is retried with
    `--unsafe-skip-dependency-check` if it fails with a dependency error.

    The ACD->L5X conversion (Logix Designer SDK) is the slow step, so if an
    identical ACD (same content hash) was already exploded under this project,
    the whole pipeline is skipped and the cached tree is reused.
    """
    project = _safe_project_name(filename)

    proj_dir = CACHE_DIR / project
    proj_dir.mkdir(parents=True, exist_ok=True)
    acd_file = proj_dir / f"{project}.acd"
    l5x_file = proj_dir / f"{project}.l5x"
    exploded_dir = proj_dir / "exploded"
    hash_file = proj_dir / ".acdhash"

    digest = hashlib.sha256(acd_bytes).hexdigest()
    if (exploded_dir / "RSLogix5000Content").is_dir() and _read_hash(hash_file) == digest:
        return project  # identical ACD already imported; skip the SDK conversion

    exe = l5xgit_exe()
    acd_file.write_bytes(acd_bytes)

    conv = _run([str(exe), "acd2l5x", "-a", str(acd_file), "-l", str(l5x_file)])
    if conv.returncode != 0 or not l5x_file.is_file():
        raise PipelineError(
            "ACD -> L5X conversion failed (is the Logix Designer SDK installed?):\n"
            f"{conv.stdout}\n{conv.stderr}".strip()
        )

    expl = _run(
        [str(exe), "explode", "-l", str(l5x_file), "-d", str(exploded_dir), "-f"]
    )
    if expl.returncode != 0:
        combined = f"{expl.stdout}\n{expl.stderr}"
        if _DEP_ERROR_RE.search(combined):
            expl = _run(
                [
                    str(exe),
                    "explode",
                    "-l",
                    str(l5x_file),
                    "-d",
                    str(exploded_dir),
                    "-f",
                    "--unsafe-skip-dependency-check",
                ]
            )
        if expl.returncode != 0:
            raise PipelineError(
                f"Exploding the L5X failed:\n{expl.stdout}\n{expl.stderr}".strip()
            )

    if not (exploded_dir / "RSLogix5000Content").is_dir():
        raise PipelineError(
            f"Explode finished but no RSLogix5000Content tree at {exploded_dir}."
        )

    try:
        hash_file.write_text(digest, encoding="utf-8")
    except OSError:
        pass  # cache-skip optimization only; failure just means we reconvert next time

    return project
