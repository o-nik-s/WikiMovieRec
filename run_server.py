"""Start WikiMovieRec API server on remote machine.

Usage:
    # Quick start (dev):
    python run_server.py

    # Production:
    python run_server.py --production

    # Custom port + model:
    WIKIMODREC_PORT=9000 WIKIMODREC_PRESET=fast python run_server.py
"""
import argparse
import os
import sys
import subprocess
import signal
import struct
import yaml


def get_python_exe():
    """Find Python executable (prefer 3.12 Keras env)."""
    candidates = [
        os.path.join(os.path.dirname(__file__), ".venv", "Scripts", "python.exe"),
        os.path.join(os.path.dirname(__file__), ".venv", "bin", "python"),
        "python3.12",
        "python3",
        "python"
    ]
    for p in candidates:
        try:
            subprocess.run([p, "--version"], capture_output=True, check=True)
            return p
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    
    print("ERROR: Python not found. Install Python 3.12 first:")
    print("  # On Ubuntu/Debian:")
    print("  sudo apt-get install python3.12 python3.12-venv")
    print("  # Create venv:")
    print("  python3.12 -m venv .venv")
    print("  source .venv/bin/activate")
    print("  pip install -r requirements.txt -r requirements-keras.txt")
    sys.exit(1)


def load_config(production=False):
    """Load configuration from YAML file."""
    config_file = "config/production.yml" if production else "config/development.yml"
    
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    else:
        # Default configuration
        config = {
            "server": {
                "host": "0.0.0.0" if production else "127.0.0.1",
                "port": 8000,
                "workers": 4 if production else 1,
                "reload": not production
            },
            "model": {
                "preset": "fast",
                "backend": "keras",
                "source": "imdb"
            }
        }
    
    # Set environment variables from config
    if "server" in config:
        os.environ.setdefault("WIKIMODREC_HOST", config["server"].get("host", "0.0.0.0"))
        os.environ.setdefault("WIKIMODREC_PORT", str(config["server"].get("port", 8000)))
        os.environ.setdefault("WIKIMODREC_WORKERS", str(config["server"].get("workers", 1)))
    
    if "model" in config:
        os.environ.setdefault("WIKIMODREC_PRESET", config["model"].get("preset", "fast"))
        os.environ.setdefault("WIKIMODREC_BACKEND", config["model"].get("backend", "keras"))
        os.environ.setdefault("WIKIMODREC_SOURCE", config["model"].get("source", "imdb"))
    
    return config


def install_dependencies():
    """Check and install dependencies."""
    py = get_python_exe()
    result = subprocess.run(
        [py, "-c", "import fastapi, uvicorn, sklearn, numpy, pandas"],
        capture_output=True,
    )
    if result.returncode != 0:
        print("Installing dependencies...")
        subprocess.run([py, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
        print("Dependencies installed.")
    else:
        print("Dependencies OK.")


def check_models():
    """Check if trained models exist."""
    models_dir = os.path.join(os.path.dirname(__file__), "models")
    if not os.path.isdir(models_dir):
        print("WARNING: No models/ directory. Train a model first:")
        print("  python scripts/train_model.py --preset fast")
        return False
    models = [f for f in os.listdir(models_dir) if f.endswith(".pkl")]
    if not models:
        print("WARNING: No .pkl files in models/. Train a model first:")
        print("  python scripts/train_model.py --preset fast")
        return False
    for m in models:
        sz = os.path.getsize(os.path.join(models_dir, m)) / 1024 / 1024
        print(f"  {m} ({sz:.1f} MB)")
    return True


def check_imdb_data():
    """Check if IMDb data exists."""
    imdb_dir = os.path.join(os.path.dirname(__file__), "data", "imdb")
    if not os.path.isdir(imdb_dir):
        print("WARNING: No IMDb data. Download first:")
        print("  python scripts/update_data.py --imdb")
        return False
    files = os.listdir(imdb_dir)
    if len(files) < 3:
        print("WARNING: IMDb data incomplete. Run:")
        print("  python scripts/update_data.py --imdb")
        return False
    print(f"IMDb data OK ({len(files)} files)")
    return True


def run_server(config):
    """Start the API server."""
    py = get_python_exe()
    
    # Load environment variables from .env file
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())
    
    host = os.environ.get("WIKIMODREC_HOST", config["server"].get("host", "0.0.0.0"))
    port = int(os.environ.get("WIKIMODREC_PORT", config["server"].get("port", 8000)))
    workers = int(os.environ.get("WIKIMODREC_WORKERS", config["server"].get("workers", 1)))
    reload = config["server"].get("reload", False)
    
    cmd = [py, "-m", "uvicorn", "src.api:create_app", "--host", host,
           "--port", str(port)]
    
    if workers > 1:
        cmd.extend(["--workers", str(workers)])
    
    if reload:
        cmd.append("--reload")
    
    print(f"Starting server on {host}:{port} (workers: {workers}, reload: {reload})")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"Server error: {e}")
        sys.exit(1)


def install_windows_service():
    """Install as Windows service using nssm (or simple alternative)."""
    py = get_python_exe()
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "run_server.py"))
    workdir = os.path.dirname(__file__)

    print("=== WikiMovieRec Windows Service Setup ===")
    print()
    print("Option 1: Using nssm (recommended):")
    print(f"  nssm install WikiMovieRec {py} {script} --production")
    print(f"  nssm set WikiMovieRec AppDirectory {workdir}")
    print("  nssm start WikiMovieRec")
    print()
    print("Option 2: Manual batch file:")
    bat_path = os.path.join(workdir, "start_server.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(f"@echo off\n")
        f.write(f"cd /d \"{workdir}\"\n")
        f.write(f"\"{py}\" {script} --production\n")
    print(f"  Created: {bat_path}")
    print(f"  Schedule with Task Scheduler or run directly")
    print()
    print("Option 3: systemd (Linux):")
    service_path = os.path.join(workdir, "wikimovierec.service")
    venv_py = os.path.join(workdir, ".venv", "bin", "python")
    with open(service_path, "w", encoding="utf-8") as f:
        f.write("""[Unit]
Description=WikiMovieRec API Server
After=network.target

[Service]
Type=simple
User=%i
WorkingDirectory={workdir}
ExecStart={py} {script} --production
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
""".format(workdir=str(workdir), py=venv_py, script=script))
    print(f"  Created template: {service_path}")
    print(f"  cp {service_path} /etc/systemd/system/")
    print("  sudo systemctl daemon-reload")
    print("  sudo systemctl enable --now wikimovierec")


def main():
    parser = argparse.ArgumentParser(description="WikiMovieRec Server")
    parser.add_argument("--production", action="store_true", help="Production mode (multiple workers)")
    parser.add_argument("--host", default=os.environ.get("WIKIMODREC_HOST", "0.0.0.0"), help="Bind host")
    parser.add_argument("--port", type=int, default=int(os.environ.get("WIKIMODREC_PORT", "8000")), help="Port")
    parser.add_argument("--workers", type=int, default=2, help="Worker count (production)")
    parser.add_argument("--check", action="store_true", help="Check setup and exit")
    parser.add_argument("--install-service", action="store_true", help="Show service install instructions")
    args = parser.parse_args()

    if args.install_service:
        install_windows_service()
        return

    print("=== WikiMovieRec Setup Check ===")
    print()
    
    # Load configuration
    config = load_config(args.production)
    
    install_dependencies()
    print()
    data_ok = check_imdb_data()
    print()
    model_ok = check_models()
    print()

    if args.check:
        if data_ok and model_ok:
            print("Setup OK. Ready to start.")
        else:
            print("Setup incomplete.")
            sys.exit(1)
        return

    if not model_ok:
        print("ERROR: No trained models. Cannot start API.")
        sys.exit(1)

    print(f"Starting server (production: {args.production})...")
    print()
    run_server(config)


if __name__ == "__main__":
    main()