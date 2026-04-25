# Kubuntu Migration Checklist

End-to-end migration plan for moving the Epidemic_Lab / Bloodplague workflow
from Windows 10 to Kubuntu 24.04 LTS on the existing MSI MS-7B33 workstation
(i5-8400, 16 GB DDR4, GTX 1660 Ti, 3 SSDs).

This is an ordered checklist. Follow it top to bottom.

---

## Phase 0 — Before you wipe Windows

Do NOT skip any of these. Once Windows is gone, recovering anything below is
painful or impossible.

- [ ] **Push everything to GitHub.** From the Epidemic_Lab directory, run
      `git status` and confirm the working tree is clean. If anything is
      uncommitted, commit and push it before going further.
- [ ] **Back up `.env`** to an external drive or password manager. It contains
      local deployment-protection bypass tokens that are NOT in git (the
      `.env.example` template only has empty placeholders).
- [ ] **Back up local logs.** The `logs/` directory holds ~4.4 GB of soak-run
      telemetry that is gitignored. Copy it to an external drive if you want
      to keep historical runs:
      ```bash
      cp -r "/e/CODE PROKECTS/Epidemic_Lab/logs" /path/to/backup/epidemic-logs
      ```
- [ ] **Back up Claude Code memory and project state.** This carries your
      assistant's long-term memory and conversation history across the OS
      switch. Copy the entire `.claude` directory:
      ```bash
      cp -r "/c/Users/bluem/.claude" /path/to/backup/dot-claude-backup
      ```
      The critical subdirectory is
      `.claude/projects/E--CODE-PROKECTS-Epidemic-Lab/memory/` — that's the
      curated long-term memory (user profile, project context, collaboration
      preferences, external resources).
- [ ] **Back up Obsidian vault** if it lives on the system drive.
- [ ] **Back up Ollama models** to skip re-downloading 4–10 GB of weights:
      ```bash
      cp -r "/c/Users/bluem/.ollama/models" /path/to/backup/ollama-models
      ```
- [ ] **Note your local C2 server URL and bypass tokens** somewhere outside
      `.env` — you will need them when restoring `.env` on Kubuntu.
- [ ] **In Windows: disable Fast Startup.** Control Panel → Power Options →
      "Choose what the power buttons do" → uncheck "Turn on fast startup".
      Required so Linux can mount NTFS partitions cleanly.
- [ ] **In BIOS: disable Secure Boot.** Saves the MOK enrollment dance during
      NVIDIA driver install. Can re-enable later if desired.
- [ ] **In BIOS: confirm UEFI mode.** Not legacy CSM.
- [ ] **Physically identify each SSD** and decide the layout:
      - 120 GB Hikvision → keep Windows 10 here for WoW / emergency fallback
      - 500 GB Samsung 850 EVO → install Kubuntu here (best drive for the OS)
      - 500 GB Crucial BX500 → shared data / VM images / Epidemic_Lab logs

---

## Phase 1 — Install Kubuntu 24.04 LTS

- [ ] Download Kubuntu 24.04.x LTS ISO from kubuntu.org
- [ ] Flash to a USB stick with Rufus (Windows) or balenaEtcher
- [ ] Boot from USB
- [ ] **Recommended safety move:** physically unplug the Hikvision (Windows)
      and Crucial (data) SSDs during install. Only the Samsung is connected.
      This makes it impossible to overwrite Windows by accident.
- [ ] In the installer, choose **manual partitioning** (the "something else"
      option) targeting the Samsung SSD only. Create exactly three partitions:
      - **`/boot/efi`** — 512 MB, FAT32, mount point `/boot/efi`, flags `boot`
        and `esp`. **This is a dedicated EFI partition for Kubuntu, separate
        from the Windows EFI partition on the Hikvision SSD.** Sharing EFI
        partitions across operating systems is a known footgun: Windows
        Updates have a documented history of removing non-Windows boot
        entries from a shared EFI partition. A dedicated EFI on the same
        physical disk as the Linux install avoids this entirely.
      - **`swap`** — 8 GB Linux swap (skip entirely if you do not care about
        hibernation; the modern alternative is a swap file managed by the OS).
      - **`/`** — rest of the Samsung, ext4, mount point `/`.
- [ ] Set up your user account (this user will need to be in the `docker`
      group later — the username is referenced from then on)
- [ ] Complete install, reboot, plug the other SSDs back in
- [ ] First boot — confirm KDE Plasma loads, network works, you can log in
- [ ] In BIOS, set boot order so the Samsung SSD's Kubuntu entry is default,
      with Windows on Hikvision still selectable from the boot menu (F8/F12
      depending on your BIOS — common on MSI is F11)

---

## Phase 2 — System update and GPU drivers

- [ ] Open a terminal (Konsole) and update the system:
      ```bash
      sudo apt update && sudo apt full-upgrade -y
      ```
- [ ] Install essential build tools:
      ```bash
      sudo apt install -y git curl wget build-essential
      ```
- [ ] Install the proprietary NVIDIA driver:
      ```bash
      sudo ubuntu-drivers autoinstall
      sudo reboot
      ```
- [ ] After reboot, verify the GPU driver works:
      ```bash
      nvidia-smi
      ```
      Expected: a table showing GTX 1660 Ti, driver version, VRAM usage. If
      this fails, STOP and fix it before continuing — Ollama will be useless
      on CPU.

---

## Phase 3 — Docker Engine

- [ ] Remove any conflicting old packages:
      ```bash
      sudo apt remove docker docker-engine docker.io containerd runc 2>/dev/null
      ```
- [ ] Install Docker from the official repository (NOT `docker.io`, NOT snap):
      ```bash
      sudo apt install -y ca-certificates curl gnupg lsb-release
      sudo install -m 0755 -d /etc/apt/keyrings
      curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
      sudo chmod a+r /etc/apt/keyrings/docker.gpg

      echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu noble stable" | \
        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

      sudo apt update
      sudo apt install -y docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
      ```
- [ ] Test:
      ```bash
      sudo docker run hello-world
      ```
- [ ] Add yourself to the `docker` group so you do not need `sudo`:
      ```bash
      sudo usermod -aG docker $USER
      ```
- [ ] **Log out completely and log back in.** A new terminal is NOT enough —
      group membership only takes effect at login. Reboot if unsure.
- [ ] Verify rootless Docker works:
      ```bash
      docker run hello-world      # no sudo
      docker compose version      # should print v2.x.x
      ```

**Security note:** anyone in the `docker` group has effective root via volume
mounts. Fine on a single-user dev box; do not add untrusted users.

---

## Phase 4 — NVIDIA Container Toolkit

Required so Docker containers (and Ollama if containerized) can use the GPU.

- [ ] Add the NVIDIA Container Toolkit repo and install:
      ```bash
      curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
        sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

      curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

      sudo apt update
      sudo apt install -y nvidia-container-toolkit
      sudo nvidia-ctk runtime configure --runtime=docker
      sudo systemctl restart docker
      ```
- [ ] Verify GPU passthrough works inside a container:
      ```bash
      docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
      ```
      Should print the same nvidia-smi table from inside the container.

---

## Phase 5 — Ollama (host install, recommended)

- [ ] Install Ollama:
      ```bash
      curl -fsSL https://ollama.com/install.sh | sh
      ollama --version
      ```
- [ ] Restore Ollama models from backup (if you backed them up in Phase 0):
      ```bash
      cp -r /path/to/backup/ollama-models/* ~/.ollama/models/
      ```
      Otherwise pull fresh:
      ```bash
      ollama pull llama3.2:latest
      ollama pull dolphin-mistral:latest
      ```
- [ ] Test inference uses the GPU:
      ```bash
      ollama run llama3.2 "say hi"
      # In another terminal:
      nvidia-smi
      # Should show "ollama" in the processes list
      ```

**Linux-specific gotcha:** containers reach the host Ollama via
`host.docker.internal` only if `--add-host=host.docker.internal:host-gateway`
is set in `docker-compose.yml`. Alternatively, use `172.17.0.1` (default
Docker bridge gateway) or set `OLLAMA_HOST=0.0.0.0` and use the host's LAN IP.
Check `docker-compose.yml` after first boot — if agents cannot reach Ollama,
this is why.

---

## Phase 6 — Python and Node toolchains

- [ ] Python (Kubuntu 24.04 ships 3.12):
      ```bash
      sudo apt install -y python3-pip python3-venv python3-dev pipx
      pipx ensurepath
      ```
- [ ] (Optional) Python 3.13 via deadsnakes if any tooling requires it:
      ```bash
      sudo add-apt-repository ppa:deadsnakes/ppa -y
      sudo apt update
      sudo apt install -y python3.13 python3.13-venv python3.13-dev
      ```
- [ ] Node via nvm (do NOT use `apt install nodejs` — too old for Vite):
      ```bash
      curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
      source ~/.bashrc
      nvm install --lts
      nvm use --lts
      node --version    # v20.x
      ```

---

## Phase 7 — Clone and bring up Epidemic_Lab

- [ ] Pick a project location and clone with submodules:
      ```bash
      mkdir -p ~/code && cd ~/code
      git clone --recurse-submodules https://github.com/Mosalah992/Bloodplague.git
      cd Bloodplague
      ```
- [ ] Restore `.env` from backup, OR copy the template and fill it in:
      ```bash
      # From backup:
      cp /path/to/backup/.env .env

      # OR from template:
      cp .env.example .env
      nano .env   # fill in local_PROTECTION_BYPASS, local_AUTOMATION_BYPASS_SECRET, C2_BEACON_SERVER_URL
      ```
- [ ] Restore `logs/` from backup if you want historical soak data:
      ```bash
      cp -r /path/to/backup/epidemic-logs ~/code/Bloodplague/logs
      ```
- [ ] Create a Python venv and install host-side dependencies:
      ```bash
      python3 -m venv .venv
      source .venv/bin/activate
      pip install -r requirements.txt
      ```
- [ ] Bring up the stack:
      ```bash
      docker compose up -d --build
      docker compose ps
      docker compose logs -f orchestrator
      ```
      All services (`redis`, `orchestrator`, `courier-1/2`, `analyst-1/2`,
      `guardian`) should reach `healthy`.
- [ ] Open the dashboard at http://localhost:8000
- [ ] (Optional) Bring up the Pixel Lab frontend in dev mode:
      ```bash
      cd frontend
      npm install
      npm run dev
      ```
      Visit http://localhost:5173

---

## Phase 8 — Restore Claude Code memory

This is the step that lets the AI assistant remember everything from prior
conversations (user profile, project context, collaboration preferences,
external resources).

- [ ] Install Claude Code (follow instructions at claude.com/claude-code).
- [ ] Run Claude Code once inside the project directory so it creates the
      project folder under `~/.claude/projects/`:
      ```bash
      cd ~/code/Bloodplague
      claude
      # exit immediately with /quit
      ```
- [ ] Find the new encoded project folder name:
      ```bash
      ls ~/.claude/projects/ | grep -i bloodplague
      # Likely: -home-<user>-code-Bloodplague
      ```
- [ ] Copy the saved memory directory into the new location (replace
      `<encoded>` with what the previous command showed):
      ```bash
      cp -r /path/to/backup/dot-claude-backup/projects/E--CODE-PROKECTS-Epidemic-Lab/memory \
            ~/.claude/projects/<encoded>/memory
      ```
- [ ] Verify the memory is loaded — start a new Claude Code session in the
      project and ask it something only the memory would know, e.g. "what
      hardware am I running this on?" or "what does Epidemic_Lab do?". If
      the answer references the GTX 1660 Ti or the strain model without you
      explaining either, the memory restore worked.

**What the memory contains** (4 files in `memory/`):
- `user_profile.md` — hardware, role, preferences, Linux experience
- `project_epidemic_lab.md` — architecture, strain model, CLAUDE.md rules
- `feedback_collaboration_style.md` — how Mo wants the assistant to work
- `reference_external_resources.md` — GitHub repo, submodules, local C2

**Honest caveat:** even with memory restored, model weights do not carry
conversation state. Each new session starts blank except for what is loaded
from `MEMORY.md` and project files. The memory system is curated facts and
preferences, not continuous consciousness — it works like a colleague reading
a briefing doc before every meeting.

---

## Phase 9 — Daily-driver tools

Quality-of-life installs you will want immediately.

- [ ] Terminal and system tools:
      ```bash
      sudo apt install -y htop btop ncdu tmux jq tree ripgrep fd-find net-tools
      ```
- [ ] KDE-friendly extras:
      ```bash
      sudo apt install -y kate krusader filelight
      ```
- [ ] Discord and Obsidian via Flatpak:
      ```bash
      sudo apt install -y flatpak plasma-discover-backend-flatpak
      flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
      flatpak install -y flathub com.discordapp.Discord
      flatpak install -y flathub md.obsidian.Obsidian
      ```
- [ ] Restore your Obsidian vault from backup if you had one.
- [ ] (Optional) Lazydocker — TUI for managing the Epidemic_Lab containers:
      ```bash
      curl https://raw.githubusercontent.com/jesseduffield/lazydocker/master/scripts/install_update_linux.sh | bash
      ```

---

## Phase 10 — Gaming (World of Warcraft)

- [ ] Install Lutris from Discover (or `sudo apt install lutris`)
- [ ] In Lutris, search for "World of Warcraft" → run the install script.
      It handles Battle.net + Proton automatically.
- [ ] First launch will download Battle.net and update WoW — large download.
- [ ] Performance should be near-native on the GTX 1660 Ti via DXVK.

---

## Verification — what success looks like

When the migration is complete you should be able to:

- [ ] Run `nvidia-smi` and see the GTX 1660 Ti with the proprietary driver
- [ ] Run `docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi` successfully
- [ ] Run `ollama run llama3.2 "test"` and see GPU usage in `nvidia-smi`
- [ ] Run `docker compose up -d --build` in `~/code/Bloodplague` and reach
      all-healthy state
- [ ] Open http://localhost:8000 and see the dashboard
- [ ] Open http://localhost:5173 and see Pixel Lab
- [ ] Start a new Claude Code session and have the assistant correctly recall
      project context without re-explaining
- [ ] Boot Windows from the Hikvision SSD via the BIOS boot menu when needed
      for WoW

---

## Rollback plan

If anything in Phases 1–7 goes catastrophically wrong:

1. Boot from the Kubuntu USB in **try without installing** mode
2. Mount the Hikvision SSD and verify Windows is intact
3. Use BIOS boot menu to boot Windows directly
4. Resume work on Windows while diagnosing the Linux issue at leisure

Because the install only touched the Samsung SSD (and the Hikvision was
physically unplugged during install), Windows on Hikvision is untouched and
fully bootable as long as you select it in the BIOS boot menu.
