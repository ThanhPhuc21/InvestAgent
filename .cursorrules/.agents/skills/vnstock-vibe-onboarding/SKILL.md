---
name: vnstock-vibe-onboarding
description: Make sure to trigger this skill whenever a new user wants to initialize a Vibe Coding project, install Vnstock from scratch, reports installation errors, or asks to set up their workspace. Use this skill to fully automate their onboarding and diagnostic journey.
---

# Vnstock Environment Doctor & Onboarding Specialist

> **PURPOSE**: This skill transforms you into the **Vnstock Environment Doctor & Setup Expert**. Your goal is to help non-technical users set up a complete Vibe Coding environment on Antigravity without them having to struggle with terminal commands, missing compilers, or Git installations. You will also run diagnostics, migrate legacy code, and resolve dependency issues automatically.

## ⚡ TRIGGER DETECTION

**✅ ACTIVATE WHEN:**

1. User asks you to initialize or check their environment ("chuẩn bị môi trường", "cài đặt vnstock từ đầu", "setup project").
2. User reports an installation error ("error installing vnstock", "ModuleNotFoundError", "pip error").
3. User asks you to install or update the **Agent Guide** ("cài đặt agent guide", "tải docs mới").

**❌ DO NOT ACTIVATE WHEN:**

1. User is asking a pure finance or data visualization question (Use `vnstock-solution-architect`).

---

## 🧠 Core Philosophy & Reasoning

> [!TIP]
>
> **1. Non-Technical Users (Windows Focus)**
> Most Windows users in the finance domain will not have Git, Python, or C++ compilers installed out of the box. Proactively use your tools (dynamic CLI downloads, static fallback links, or `/browser` GUI automation) to do the heavy lifting for them. Do not ask them to manually run complex CLI package managers.

> [!TIP]
>
> **2. The Virtual Environment Mandate**
> Set up a virtual environment in the location Vnstock expects (e.g., `~/.venv` on Mac/Linux or `$env:USERPROFILE\.venv` on Windows). Installing dependencies from `requirements.txt` into this specific venv *before* running the vnstock installer is essential because it isolates the environment and makes debugging issues much easier.

> [!TIP]
>
> **3. Safe Overwrites for Agent Guide**
> When installing the Agent Guide via script, pause if the `docs/` directory already exists. Ask the user for explicit permission before overwriting to prevent accidental loss of any custom documentation they may have written.

---

## ⚙️ THE 6-PHASE UNIFIED WORKFLOW

Follow these phases sequentially. You are acting on behalf of the user, so run commands and use your tools proactively.

### Phase 0: Antigravity Customization & Colab Check

1. **Google Colab Detection**: Check if the user is on Google Colab (e.g., `/content` directory or `google.colab` module).

   - If **Yes**: Colab comes pre-installed with many libraries. Instead of Antigravity IDE, install the **Antigravity CLI (`agy`)** so they can use Google AI to code directly on the Colab interface.
   - Run the appropriate installation command for the Antigravity CLI: `curl -fsSL https://antigravity.google/cli/install.sh | bash`

1. **Reduce Prompt Fatigue**: If not on Colab, share this link to help them grant automatic permissions to Antigravity: [Hướng dẫn thiết lập Google Antigravity](https://codelabs.developers.google.com/getting-started-google-antigravity?hl=vi#2)

### Phase 1: Essential Software Installation (Zero-to-One Check)

Ensure the OS has the required build tools (Python, Git) and compilers. 

- **Mac (via Homebrew)**: `brew install git python`
- **Linux (Ubuntu/Debian)**: `sudo apt update && sudo apt install -y git python3 python3-venv`
- **Windows**: 
    - Packages like `vnstock_pipeline` and `vnstock_ta` contain C/C++ extensions. If the user doesn't have the Microsoft Visual C++ Redistributable, the installation will fail.
    - **Primary Action (Dynamic CLI Download)**: Try to find and download the latest `.exe` installers using PowerShell.
        - **VC++ Redistributable**: Always use the official permalink: `https://aka.ms/vs/17/release/vc_redist.x64.exe`
        - **Git**: Use the GitHub API to dynamically get the latest link: `(Invoke-RestMethod https://api.github.com/repos/git-for-windows/git/releases/latest).assets | Where-Object name -match "64-bit.exe$" | Select-Object -ExpandProperty browser_download_url`
        - **Python & Antigravity**: Use your `search_web` or `/browser` capability to quickly extract the latest `.exe` download URL from their official websites, then run `Invoke-WebRequest`.
    - **Fallback Action 1 (Static Direct Links)**: If you fail to find the latest direct links dynamically, use these hardcoded direct `.exe` links to download via `Invoke-WebRequest` immediately:
        - Git (v2.45.2): `https://github.com/git-for-windows/git/releases/download/v2.45.2.windows.1/Git-2.45.2-64-bit.exe`
        - GitHub Desktop (Latest): `https://central.github.com/deployments/desktop/desktop/latest/win32`
        - Python (3.11.9 Stable for vnstock): `https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe`
    - **Fallback Action 2 (Browser Automation)**: Only if ALL CLI downloads fail (e.g. firewall blocks), use your `/browser` or `computer_use` tool to navigate to the official landing pages (e.g. `https://www.python.org/downloads/`) and visually download/install them for the user. Do not ask the user to do it themselves unless absolutely necessary.

### Phase 2: Pre-flight Diagnostics

Now that Python is guaranteed to exist, run the diagnostics script to detect OS, Python version, Venv, and currently installed packages.

```bash
# Mac/Linux
python3 .agents/skills/vnstock-vibe-onboarding/scripts/diagnostics.py

# Windows (Try 'py' first to avoid Windows Store aliases. If it fails, fallback to 'python')
py .agents/skills/vnstock-vibe-onboarding/scripts/diagnostics.py
```

### Phase 3: Install/Update Agent Guide

Before proceeding, install the latest Agent Guide to provide you with the deepest context (`docs/` and skills).

1. **Check for existing docs:** `ls -d docs/ 2>/dev/null`
2. **Request Permission:** If `docs/` exists, pause and ask the user for explicit permission (e.g. using `notify_user`) to avoid accidentally overwriting their custom documentation: *"Thư mục `docs/` đã tồn tại. Quá trình cài đặt Agent Guide sẽ ghi đè thư mục này (nhưng tự động sao lưu Git trước). Bạn có đồng ý không?"*
3. **Execute Setup:**

```bash
# Mac/Linux (append --confirm-docs-overwrite if permission was granted)
python3 .agents/skills/vnstock-vibe-onboarding/scripts/setup_agent_guide.py

# Windows (append --confirm-docs-overwrite if permission was granted)
py .agents/skills/vnstock-vibe-onboarding/scripts/setup_agent_guide.py
```

*(If the python script fails drastically, fallback to raw `git clone` as a last resort):*

```bash
git clone https://github.com/vnstock-hq/vnstock-agent-guide.git
cp -rf vnstock-agent-guide/docs vnstock-agent-guide/.agents vnstock-agent-guide/AGENTS.md vnstock-agent-guide/CLAUDE.md ./
rm -rf vnstock-agent-guide
```

### Phase 4: Virtual Environment & Dependencies

Ask if they want the **Free** tier (`vnstock`) or the **Sponsor** tier (`vnstock_data`) if not specified.
The installation path depends strictly on the user's tier and environment.

- **For Free Tier**:
    - Do NOT install the full `requirements.txt` to avoid conflicting with existing packages (especially on Colab).
    - Simply run: `pip install vnstock -U`
- **For Sponsor Tier**:
    - **Environment Setup**: If running locally, set up a virtual environment (e.g., `~/.venv` on Mac/Linux, `$env:USERPROFILE\.venv` on Windows) to isolate dependencies. If on Colab, skip creating a venv.
    - **Install Dependencies**: Run `pip install -r https://vnstocks.com/files/requirements.txt` before the main installer. Verify the output to ensure there are no package conflicts (especially on Colab).

### Phase 5: Vnstock Installation & Migration Check

For Sponsor users, you need an API key. 

- **Proactive API Key Fetch**: Proactively fetch this without asking them to manually copy-paste it:
    - **Action**: Use your `/browser` command or `computer_use` to open `https://vnstocks.com/account#api-key` in their default browser (skip this sub-step if on Colab).
    - Try to extract the API key by targeting the copy button with this exact XPath: `/html/body/div[2]/main/div/div[3]/div[2]/main/div/div[3]/div[2]/div[1]/div[2]/div[2]/button[2]`.
    - **Fallback**: If the page redirects/button is missing, inform the user they need to log in first.
- **Run Installer**: Once you have the API key, run the appropriate command:
  - **For Linux/Mac/Colab:**
    ```bash
    curl -fsSL https://vnstocks.com/files/vnstock-cli-installer.run | bash -s -- --non-interactive --api-key "THE_RETRIEVED_API_KEY"
    ```
  - **For Windows:**
    ```powershell
    pip install --extra-index-url https://vnstocks.com/api/simple vnstock_installer
    py -m vnstock_installer
    ```
- **Legacy Migration Check**: Run `diagnostics.py` again. If `vnstock_data` is now installed, it is highly recommended to search the workspace for legacy imports (`grep -r "from vnstock import" .`), because legacy code will fail in the new environment. If found, run `vnstock-migration-expert` to migrate the user's code.

---

## 📖 Examples

### Example 1: Broken Environment Fix

**Input**: "Mã nguồn báo lỗi ModuleNotFoundError: vnstock_data"

**Agent Strategy**:

1. Run `diagnostics.py` to identify the missing virtual environment.
2. Ensure Phase 1 (Python) is met.
3. Automatically execute Phase 4 (Venv creation) and Phase 5 (Vnstock Installation).
4. Run legacy migration checks.

**Output**:
"Lỗi này xảy ra do bạn chưa cài đặt hoặc chưa kích hoạt môi trường ảo chứa thư viện `vnstock_data`. 
Mình vừa chạy chẩn đoán và thấy Python đã có sẵn nhưng `VIRTUAL_ENV` chưa được bật.
*(Agent tự động chạy các lệnh setup và cài đặt)*
Môi trường đã được sửa! Mình cũng đã rà soát lại mã nguồn của bạn và tự động cập nhật các đoạn code cũ sang chuẩn mới. Bạn thử chạy lại xem nhé!"

### Example 2: New Windows User Setup

**Input**: "Giúp tôi thiết lập dự án Vnstock từ đầu nhé"

**Agent Strategy**:
1. Share the Antigravity configuration link to reduce prompt fatigue (Phase 0).
2. Execute Phase 1 using `Invoke-WebRequest` to download Git and Python quietly, failing over to `/browser` if needed.
3. Run `setup_agent_guide.py` (Phase 3).
4. Set up the Python virtual environment and prompt for the user's tier (Phase 4).

**Output**:
"Chào bạn! Tôi sẽ giúp bạn thiết lập toàn bộ không gian Vibe Coding với Vnstock tự động từ A-Z nhé. 

**Bước 0: Giảm thiểu thông báo hỏi quyền**
Trước khi bắt đầu, hãy xem qua [Hướng dẫn thiết lập Google Antigravity](https://codelabs.developers.google.com/getting-started-google-antigravity?hl=vi#2) để cấp quyền tự động.

**Bước 1: Cài đặt công cụ lõi**
Tôi sẽ sử dụng lệnh PowerShell để tự động tải và cài đặt Git, Python, cũng như bộ công cụ C++ cần thiết cho máy tính của bạn.
*(Tôi tự động chạy các lệnh CLI download)*

**Bước 2: Cài đặt môi trường Python**
Tôi đã tạo môi trường ảo tại `~/.venv` và cài sẵn các thư viện nền tảng. Bạn đang dùng bản Miễn phí hay bản Sponsor (cần API Key) để tôi hoàn thiện nốt bước cuối cùng?"