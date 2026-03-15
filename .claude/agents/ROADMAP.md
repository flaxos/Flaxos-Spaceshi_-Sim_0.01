# Flax's Homelab: Assessment, Roadmap & Vision

## Context for Claude Code

You are helping Flax assess, plan, and incrementally improve a home lab environment. Flax is a Customer Solutions Manager (not an engineer) who is technically capable but self-taught. He's been away from the homelab scene for ~10 years and is rebuilding from scratch on Linux.

**Key principles:**
- NEVER break what's currently working. All changes must be additive and reversible.
- Explain the "why" in plain language, not just the "how."
- Treat this as an iterative project — small wins, not a big-bang migration.
- Everything should be reproducible: configs in git, services in Docker Compose files.

---

## Phase 0: Discovery (Do This First)

Before making ANY changes, run an assessment of the current environment. Claude Code should help gather and document:

### System Inventory
```bash
# Hardware
cat /proc/cpuinfo | head -20
free -h
lsblk
df -h
lspci | grep -i vga   # GPU check for future LLM work
ip addr show

# What's running
systemctl list-units --type=service --state=running
docker ps -a 2>/dev/null || echo "Docker not installed or not running"
docker compose version 2>/dev/null || echo "Docker Compose not available"

# Network
cat /etc/hosts
ss -tlnp   # listening ports
cat /etc/resolv.conf

# Existing configs worth preserving
ls -la /etc/docker/ 2>/dev/null
ls -la ~/.config/ 2>/dev/null
```

### Current State Documentation
After running discovery, create a `current-state.md` file documenting:
- Hardware specs (CPU, RAM, disk, GPU if any)
- OS version and kernel
- Services currently running (especially Ollama)
- Network configuration (static IP? DHCP? subnet?)
- Disk usage and available space
- Any existing Docker containers or compose files
- What works and must not be disrupted

---

## Phase 1: Foundations (Week 1-2)

**Goal:** Get the basics right without changing anything that's currently working.

### 1.1 — Git Everything
- [ ] Install git if not present
- [ ] Create a `~/homelab` directory
- [ ] Initialise git repo
- [ ] All future Docker Compose files and configs live here
- [ ] Create a `.gitignore` for secrets/env files
- [ ] Consider: self-hosted Gitea later, GitHub/GitLab free for now

### 1.2 — Docker & Docker Compose
- [ ] Ensure Docker is installed and running
- [ ] Ensure Docker Compose v2 is available
- [ ] Create a shared Docker network: `docker network create lab`
- [ ] Migrate any bare `docker run` commands into `docker-compose.yml` files
- [ ] Document Ollama's current setup — is it running in Docker or bare metal?

### 1.3 — First Compose Stack: Management Tools
Create `~/homelab/management/docker-compose.yml`:
- **Dozzle** — real-time container log viewer (lightweight, read-only, zero config)
- **Portainer CE** or **Komodo** — container management GUI
- **Watchtower** — automatic container updates (set to notify-only initially)

### 1.4 — Homepage Dashboard
Create `~/homelab/dashboard/docker-compose.yml`:
- **Homepage** — YAML-configured dashboard as your browser start page
- Add widgets for each service as you deploy them
- This becomes your "control panel" going forward

---

## Phase 2: Networking & Access (Week 3-4)

**Goal:** Stop memorising IP:port combos. Add a proper front door.

### 2.1 — Reverse Proxy (Traefik)
Create `~/homelab/traefik/docker-compose.yml`:
- Traefik as the single entry point for all services
- Automatic HTTPS with Let's Encrypt (even for local, use a domain + DNS challenge)
- Each service gets a subdomain: `ollama.lab.local`, `dashboard.lab.local`, etc.
- Labels on each Docker service to auto-register with Traefik

### 2.2 — DNS (Pi-hole or AdGuard Home)
Create `~/homelab/dns/docker-compose.yml`:
- Local DNS resolver pointing `*.lab.local` to your server
- Network-wide ad blocking as a bonus
- Point your router's DNS to this server

### 2.3 — VPN (WireGuard via wg-easy)
Create `~/homelab/vpn/docker-compose.yml`:
- Secure remote access to the lab from anywhere
- Web UI for managing clients (phone, laptop, etc.)
- No ports exposed except the WireGuard UDP port

### 2.4 — Authentication (Authentik) — OPTIONAL at this stage
- Centralised login for all services
- SSO across your lab
- This is more complex — skip if the above feels like enough for now

---

## Phase 3: Security & Separation (Week 5-8)

**Goal:** Move from "everything on one flat network" to proper isolation.

### 3.1 — Docker Network Segmentation
- Create separate Docker networks per trust zone:
  - `frontend` — services that face Traefik
  - `backend` — databases, internal services
  - `ai` — Ollama and related AI tools
- Services only join the networks they need
- This is the container equivalent of the "apartment building" model

### 3.2 — Firewall Rules
- Review and tighten `iptables` or `ufw` rules
- Default deny inbound
- Only Traefik listens on 80/443
- Only WireGuard listens on its UDP port
- Everything else is internal only

### 3.3 — Secrets Management
- Move all passwords/API keys into `.env` files
- `.env` files are in `.gitignore` (never committed)
- Consider: create a `.env.example` with dummy values for documentation
- Later: Vaultwarden for password management

### 3.4 — Backups
- **Duplicati** or **Restic** for automated backups
- Back up: git repo, Docker volumes, .env files
- Test restores (a backup you haven't tested is not a backup)

---

## Phase 4: AI & Productivity Stack (Week 9-12)

**Goal:** Level up the AI setup beyond basic Ollama.

### 4.1 — Ollama Optimisation
- Move Ollama into Docker Compose if not already
- Assess storage: which models fit on current disk?
- GPU passthrough if available
- Expose via Traefik with authentication

### 4.2 — Open WebUI
- ChatGPT-style interface on top of Ollama
- Conversation history, document uploads
- Multi-model switching

### 4.3 — n8n (Workflow Automation)
- Visual automation builder — connects AI to everything
- Especially relevant for process improvement work
- Can trigger Ollama, send emails, update spreadsheets, post to Slack
- This bridges your home lab skills with your work skills

### 4.4 — AnythingLLM or similar RAG tool
- Upload documents, PDFs, notes
- Chat with your own data using local models
- Great for personal knowledge management

---

## Phase 5: Long-Term Vision (3-6 months)

### Proxmox Migration
- When you're ready for full VM-level isolation
- Run Proxmox as the hypervisor on bare metal
- Create VMs by trust zone:
  - **Lab VM** — experiments, game dev, Ollama
  - **Infra VM** — Traefik, DNS, monitoring, auth
  - **Personal VM** — Nextcloud, Vaultwarden, sensitive data
- Each VM runs its own Docker stack
- If one VM gets compromised, others are isolated

### Self-Hosted Services to Consider
- **Nextcloud** — replace Google Drive/Dropbox
- **Vaultwarden** — self-hosted Bitwarden password manager
- **Immich** — Google Photos replacement
- **Paperless-ngx** — document scanning and OCR
- **Uptime Kuma** — monitoring dashboard
- **Gitea** — self-hosted Git (replace GitHub dependency)

### Hardware Upgrades (as budget allows)
- Bigger SSD/NVMe for AI models (500GB+ recommended)
- More RAM (32GB+ for comfortable LLM use)
- GPU with 12GB+ VRAM if pursuing local AI seriously
- Consider a mini PC cluster for Proxmox

---

## Rules for Claude Code Sessions

When working on this lab:

1. **Always read `current-state.md` first** to understand what exists.
2. **Never modify running services** without creating the new config alongside them first.
3. **Always use Docker Compose** — no bare `docker run` commands.
4. **Always put configs in `~/homelab/`** under git.
5. **Test before switching** — bring up new service, verify it works, then cut over.
6. **Document as you go** — update `current-state.md` after each change.
7. **Keep it simple** — if Flax can't understand the config, it's too complex.
8. **Disk space is limited** — always check `df -h` before pulling images or models.
9. **Explain trade-offs** — don't just do things, explain why this approach vs alternatives.
10. **Commit after each successful change** — small, frequent git commits with clear messages.
