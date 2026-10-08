#!/usr/bin/env python3
"""
Cross-platform firmware toolchain setup script.
Automatically installs rustup if missing, then sets up embedded toolchain.
"""
import subprocess
import sys
import os
import shutil
import platform
import urllib.request
from pathlib import Path

def is_windows():
    return platform.system() == "Windows"

def install_rustup_windows():
    """Download and run rustup-init.exe for Windows"""
    print("📥 Downloading rustup-init.exe...")
    url = "https://win.rustup.rs/x86_64"
    rustup_init = Path.home() / "rustup-init.exe"
    
    try:
        urllib.request.urlretrieve(url, rustup_init)
        print("✅ Downloaded rustup-init.exe")
        
        print("🔧 Running rustup installer (this may take a few minutes)...")
        # Run with default profile (minimal), no PATH modification (we handle that)
        result = subprocess.run(
            [str(rustup_init), "-y", "--default-toolchain", "stable", "--profile", "minimal"],
            check=True,
            capture_output=True,
            text=True
        )
        print("✅ rustup installed successfully")
        
        # Add to PATH for this session
        cargo_bin = Path.home() / ".cargo" / "bin"
        os.environ["PATH"] = f"{cargo_bin};{os.environ['PATH']}"
        
    except Exception as e:
        print(f"❌ Failed to install rustup: {e}")
        print("Please install manually from https://rustup.rs")
        sys.exit(1)
    finally:
        if rustup_init.exists():
            rustup_init.unlink()

def install_rustup_unix():
    """Download and run rustup.sh for Unix (macOS/Linux)"""
    print("📥 Downloading rustup installer...")
    url = "https://sh.rustup.rs"
    
    try:
        print("🔧 Running rustup installer (this may take a few minutes)...")
        # Pipe sh.rustup.rs directly to sh
        result = subprocess.run(
            ["curl", "--proto", "=https", "--tlsv1.2", "-sSf", url],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Run the script with -y for non-interactive
        subprocess.run(
            ["sh", "-s", "--", "-y", "--default-toolchain", "stable", "--profile", "minimal"],
            input=result.stdout,
            text=True,
            check=True
        )
        print("✅ rustup installed successfully")
        
        # Add to PATH for this session
        cargo_bin = Path.home() / ".cargo" / "bin"
        os.environ["PATH"] = f"{cargo_bin}:{os.environ['PATH']}"
        
    except Exception as e:
        print(f"❌ Failed to install rustup: {e}")
        print("Please install manually from https://rustup.rs")
        sys.exit(1)

def main():
    print("=" * 60)
    print("Lucy Firmware Toolchain Setup")
    print("=" * 60)
    
    # Step 1: Check for rustup, install if missing
    print("\n1️⃣ Checking for rustup...")
    if not shutil.which("rustup"):
        print("⚠️  rustup not found - installing automatically...")
        if is_windows():
            install_rustup_windows()
        else:
            install_rustup_unix()
        
        # Verify installation
        if not shutil.which("rustup"):
            print("❌ rustup installation failed")
            print("Please install manually from https://rustup.rs")
            sys.exit(1)
    else:
        print("✅ rustup already installed")
        # Show version
        result = subprocess.run(["rustup", "--version"], capture_output=True, text=True)
        print(f"   {result.stdout.strip()}")
    
    # Step 2: Install ARM Cortex-M0+ target for RP2040
    print("\n2️⃣ Installing thumbv6m-none-eabi target...")
    try:
        subprocess.run(
            ["rustup", "target", "add", "thumbv6m-none-eabi"],
            check=True,
            capture_output=True,
            text=True
        )
        print("✅ ARM Cortex-M0+ target installed")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install target: {e.stderr}")
        sys.exit(1)
    
    # Step 3: Install elf2uf2-rs for UF2 conversion
    print("\n3️⃣ Installing elf2uf2-rs...")
    try:
        # Check if already installed
        result = subprocess.run(
            ["cargo", "install", "--list"],
            capture_output=True,
            text=True,
            check=True
        )
        if "elf2uf2-rs" in result.stdout:
            print("✅ elf2uf2-rs already installed")
        else:
            print("   Installing elf2uf2-rs (this may take a few minutes)...")
            subprocess.run(
                ["cargo", "install", "elf2uf2-rs"],
                check=True
            )
            print("✅ elf2uf2-rs installed")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install elf2uf2-rs: {e}")
        sys.exit(1)
    
    # Step 4: Symlink/copy to Pixi environment
    print("\n4️⃣ Linking tools to Pixi environment...")
    try:
        conda_prefix = Path(os.environ.get("CONDA_PREFIX", ""))
        if not conda_prefix.exists():
            print("⚠️  CONDA_PREFIX not set - tools will only be in ~/.cargo/bin")
        else:
            cargo_bin = Path.home() / ".cargo" / "bin"
            if is_windows():
                # Windows: copy to Scripts directory
                pixi_bin = conda_prefix / "Scripts"
                pixi_bin.mkdir(exist_ok=True)
                src = cargo_bin / "elf2uf2-rs.exe"
                dst = pixi_bin / "elf2uf2-rs.exe"
                if src.exists():
                    shutil.copy(src, dst)
                    print(f"✅ Copied elf2uf2-rs.exe to {pixi_bin}")
            else:
                # Unix: symlink to bin directory
                pixi_bin = conda_prefix / "bin"
                pixi_bin.mkdir(exist_ok=True)
                src = cargo_bin / "elf2uf2-rs"
                dst = pixi_bin / "elf2uf2-rs"
                if src.exists():
                    if dst.exists():
                        dst.unlink()
                    dst.symlink_to(src)
                    print(f"✅ Symlinked elf2uf2-rs to {pixi_bin}")
    except Exception as e:
        print(f"⚠️  Warning: Could not link to Pixi environment: {e}")
        print("   Tools will still work from ~/.cargo/bin")
    
    # Step 5: Verify installation
    print("\n5️⃣ Verifying installation...")
    checks = [
        ("rustc", ["rustc", "--version"]),
        ("cargo", ["cargo", "--version"]),
        ("elf2uf2-rs", ["elf2uf2-rs", "--version"]),
    ]
    
    all_ok = True
    for name, cmd in checks:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            version = result.stdout.strip().split('\n')[0]
            print(f"✅ {name}: {version}")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"❌ {name}: NOT FOUND")
            all_ok = False
    
    print("\n" + "=" * 60)
    if all_ok:
        print("✅ Firmware toolchain setup complete!")
        print("\nNext steps:")
        print("  - Build firmware: pixi run firmware-build")
        print("  - Flash boards:   pixi run firmware-flash")
    else:
        print("❌ Setup incomplete - please fix errors above")
        sys.exit(1)
    print("=" * 60)

if __name__ == "__main__":
    main()
