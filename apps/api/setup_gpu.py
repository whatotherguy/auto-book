"""One-click GPU setup for Audiobook Editor transcription.

Run from the apps/api directory:
    python setup_gpu.py
"""
import subprocess
import sys


def run(cmd: list[str], desc: str) -> bool:
    print(f"\n{'='*60}")
    print(f"  {desc}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd, check=False)
    return result.returncode == 0


def main():
    print("Audiobook Editor — GPU Transcription Setup")
    print("=" * 60)

    # Step 1: Check current state
    print("\n[1/4] Checking current environment...\n")

    has_torch = False
    has_cuda = False
    try:
        import torch

        has_torch = True
        has_cuda = torch.cuda.is_available()
        if has_cuda:
            print(f"  CUDA available: {torch.cuda.get_device_name(0)}")
            vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"  VRAM: {vram:.1f} GB")
        else:
            print("  PyTorch found but CUDA not available.")
            print("  This could mean: no NVIDIA GPU, or PyTorch CPU-only build installed.")
    except ImportError:
        print("  PyTorch not installed.")

    has_whisper = False
    try:
        import faster_whisper

        has_whisper = True
        print(f"  faster-whisper: installed ({faster_whisper.__version__})")
    except ImportError:
        print("  faster-whisper: not installed")

    # Step 2: Install/upgrade PyTorch with CUDA
    if not has_cuda:
        print("\n[2/4] Installing PyTorch with CUDA support...")
        print("  This may take a few minutes on first install.\n")
        success = run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "torch",
                "torchaudio",
                "--index-url",
                "https://download.pytorch.org/whl/cu121",
            ],
            "Installing PyTorch with CUDA 12.1",
        )
        if not success:
            print("\n  WARNING: PyTorch CUDA install failed.")
            print(
                "  Try manually: pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121"
            )
            print(
                "  Or for CUDA 11.8: pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118"
            )
    else:
        print("\n[2/4] PyTorch CUDA already available. Skipping install.")

    # Step 3: Install faster-whisper
    if not has_whisper:
        print("\n[3/4] Installing faster-whisper...")
        run(
            [sys.executable, "-m", "pip", "install", "faster-whisper>=1.0"],
            "Installing faster-whisper",
        )
    else:
        print("\n[3/4] faster-whisper already installed. Skipping.")

    # Step 4: Download model
    print("\n[4/4] Downloading Whisper model (large-v3)...")
    print("  This is a ~3GB download on first run.\n")
    try:
        from faster_whisper import WhisperModel

        print("  Loading model to trigger download...")
        _model = WhisperModel(
            "large-v3", device="cpu", compute_type="int8", local_files_only=False
        )
        print("  Model downloaded and cached successfully.")
        del _model
    except Exception as exc:
        print(f"  Model download failed: {exc}")
        print("  The app will fall back to smaller models automatically.")

    # Final status
    print("\n" + "=" * 60)
    print("  Setup complete!")
    print("=" * 60)

    try:
        import torch

        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"\n  GPU: {gpu_name} ({vram:.1f} GB VRAM)")
            if vram >= 8:
                print("  Recommended: large-v3 model with float16")
                print("  Expected speed: ~3 minutes per hour of audio")
            elif vram >= 4:
                print("  Recommended: medium model with int8_float16")
                print("  Expected speed: ~5 minutes per hour of audio")
            else:
                print("  Recommended: small model with int8")
                print("  Expected speed: ~8 minutes per hour of audio")
            print("\n  Set WHISPERX_DEVICE=auto in .env (this is the default).")
            print("  The app will auto-detect your GPU on next analysis run.")
        else:
            print("\n  No CUDA GPU detected. Transcription will use CPU.")
            print("  CPU transcription takes ~45-60 minutes per hour of audio.")
    except ImportError:
        print("\n  PyTorch import failed. Run this script again or install manually.")


if __name__ == "__main__":
    main()
