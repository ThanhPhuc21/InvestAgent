import sys
import os
import platform
import subprocess

def check_python_version():
    major, minor = sys.version_info.major, sys.version_info.minor
    status = "✅" if major >= 3 and minor >= 10 else "❌"
    print(f"{status} Python Version: {major}.{minor} (Requires >= 3.10)")
    return major >= 3 and minor >= 10

def check_venv():
    in_venv = "VIRTUAL_ENV" in os.environ or "CONDA_PREFIX" in os.environ
    status = "✅" if in_venv else "⚠️"
    print(f"{status} Virtual Environment Active: {in_venv}")
    if in_venv:
        print(f"   -> Path: {os.environ.get('VIRTUAL_ENV') or os.environ.get('CONDA_PREFIX')}")

def get_hosting():
    if 'google.colab' in sys.modules: return "Google Colab"
    if 'CODESPACE_NAME' in os.environ: return "GitHub Codespace"
    if 'KAGGLE_CONTAINER_NAME' in os.environ: return "Kaggle"
    return "Local/Unknown"

def check_packages():
    print("\n--- Package Inventory ---")
    packages = ['vnstock', 'vnstock_data', 'vnstock_ta', 'vnstock_news', 'vnstock_pipeline', 'vnii', 'vnai']
    is_sponsor = False
    is_free = False
    
    for pkg in packages:
        try:
            mod = __import__(pkg)
            version = getattr(mod, '__version__', 'unknown')
            print(f"✅ {pkg:16} : Installed (v{version})")
            if pkg == 'vnstock': is_free = True
            if pkg == 'vnstock_data': is_sponsor = True
        except ImportError:
            print(f"❌ {pkg:16} : Not Installed")
            
    print("\n--- Tier Assessment ---")
    
    # Check for vnstock auth state
    has_auth = False
    email = "unknown"
    auth_file = os.path.join(os.path.expanduser("~"), ".vnstock", "auth_state.json")
    if os.path.exists(auth_file):
        try:
            import json
            with open(auth_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                user_info = f"{data.get('user', 'unknown')} (Tier: {data.get('tier', 'unknown')})"
                has_auth = data.get("authenticated", False)
        except Exception:
            has_auth = True
            user_info = "unknown"
            
    if is_sponsor or has_auth:
        msg = "🏆 Detected Tier: SPONSOR"
        details = []
        if has_auth: details.append(f"Auth file found for {user_info}")
        if is_sponsor: details.append("vnstock_data is present")
        print(f"{msg} ({', '.join(details)})")
    elif is_free:
        print("🌱 Detected Tier: FREE (only vnstock is present)")
    else:
        print("⚠️ Detected Tier: UNKNOWN (Ecosystem not installed, no auth file found)")


if __name__ == "__main__":
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Hosting: {get_hosting()}")
    check_python_version()
    check_venv()
    check_packages()
