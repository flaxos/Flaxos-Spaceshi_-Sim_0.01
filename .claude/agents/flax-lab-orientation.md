# Flax Lab — Orientation & Roadmap

## Where You're At Right Now ✅

| Tool | Status |
|------|--------|
| Ubuntu 24.04 + XFCE | ✅ Running |
| Firefox | ✅ |
| Node v24.14 | ✅ |
| Claude Code 2.1.71 | ✅ (needs auth) |
| Docker Engine | ✅ |
| VS Code | ✅ |
| Dual boot (Linux lab / Windows gaming) | ✅ |

---

## 1. Authenticate Claude Code

First thing. Open terminal and run:

```bash
claude
```

It will open a browser tab asking you to log in with your Anthropic account (claude.ai login).
Approve it, come back to terminal. Done. Claude Code is now auth'd.

Test it:
```bash
cd ~/vault
claude
```

Type `hello` and it should respond. That's your personal assistant running locally.

---

## 2. Understanding Docker — The Simple Version

Think of Docker like this: **it runs apps in sealed boxes.**

Each box (called a **container**) has everything the app needs inside it.
The app can't mess with your system. Your system can't mess with the app.
You can start it, stop it, delete it, rebuild it — your Linux install stays clean.

### The mental model for YOUR lab:

```
Your Linux machine (the host)
├── Your files, code, vault          ← live here, on the real disk
├── VS Code, Claude Code, Firefox    ← run directly on Linux
└── Docker containers (~/stacks/)
    ├── Home Assistant               ← home automation brain
    ├── Ollama                       ← local LLMs (runs offline)
    ├── n8n                          ← automation workflows
    └── Jupyter Lab                  ← Python experiments
```

### The golden rule:
- **Build and edit code** → do it locally (VS Code + Claude Code)
- **Run services** → do it in Docker (Home Assistant, Ollama, n8n etc.)
- **Your personal files and vault** → always local, never inside a container

### Key Docker commands you'll actually use:

```bash
# Start a stack (run from inside the stack's folder)
docker compose up -d

# Stop a stack
docker compose down

# See what's running
docker ps

# See logs from a container
docker compose logs -f

# Completely wipe and restart a container (keeps your data)
docker compose down && docker compose up -d
```

---

## 3. VS Code — Essential Extensions

Open VS Code (`code .` from terminal or find it in the app menu).
Press `Ctrl+Shift+X` to open extensions. Install these:

### Must-have
| Extension | Why |
|-----------|-----|
| **Python** (Microsoft) | Python dev, Notion scripts, Home Assistant |
| **Docker** (Microsoft) | Manage containers visually inside VS Code |
| **GitLens** | Visual git history and blame |
| **YAML** | Editing Docker compose files without pain |
| **Remote - SSH** | Connect to other machines from VS Code later |
| **Prettier** | Auto-format code on save |

### Recommended for your projects
| Extension | Why |
|-----------|-----|
| **REST Client** | Test APIs (Notion, Home Assistant) without Postman |
| **Thunder Client** | Alternative to REST Client, more visual |
| **Markdown Preview Enhanced** | Preview your vault .md files |
| **Todo Tree** | Finds all TODO comments across your projects |
| **GitHub Copilot** | Optional — you have Claude Code but some like both |

### How Claude Code and VS Code work together

They are **separate tools that complement each other**:

```
VS Code                          Claude Code (terminal)
──────────────────────────────   ──────────────────────────────
Browse and edit files visually   Agent that reads/writes files
See git changes                  Runs tasks autonomously
Run extensions                   Executes multi-step plans
Debug code                       Searches across your codebase
```

**The workflow:**
1. Open VS Code in your project folder (`code ~/vault` or `code ~/stacks/home-assistant`)
2. Open a terminal inside VS Code (`Ctrl+~`)
3. Run `claude` in that terminal
4. You now have Claude Code running WITH visibility of your files in the same window
5. Ask Claude to do things — you watch the files change in VS Code in real time

This is the core loop. It's very powerful once you feel it.

---

## 4. How Your Projects Map to This Environment

```
PROJECT                 WHERE IT LIVES          TOOLS
──────────────────────────────────────────────────────────────
Personal Assistant      ~/vault/                Claude Code + VS Code
                        (markdown files)        Obsidian (for reading)

Life OS / Notion MCP    ~/projects/life-os/     Claude Code + VS Code
                        (scripts + config)      Notion MCP server in Docker

Home Automation         ~/stacks/home-assistant/ Docker + VS Code
                        (Docker container)      Home Assistant web UI

Ollama (local LLMs)     ~/stacks/ollama/        Docker
                        (Docker container)      Open WebUI in browser

n8n (automation)        ~/stacks/n8n/           Docker
                        (Docker container)      n8n web UI in browser

Pizzatorio / game dev   ~/projects/pizzatorio/  VS Code + Python
                        (Python code)           Claude Code for refactors

Flax Spaceship Sim      ~/projects/spaceship/   VS Code + Python
                        (Python code)           Claude Code
```

---

## 5. Revised Roadmap — In Order

### Phase 1: Foundation (You Are Here)
- [x] Ubuntu + GUI installed
- [x] Node, Docker, VS Code, Claude Code installed
- [ ] **Authenticate Claude Code** ← do this now
- [ ] Log out and back in (activate Docker group properly)
- [ ] Install VS Code extensions above
- [ ] Open `~/vault` in VS Code, open terminal, run `claude`, type `/init`
- [ ] Edit `~/vault/CLAUDE.md` with your name and goals

### Phase 2: Personal Assistant (this week)
- [ ] Complete CLAUDE.md personalisation
- [ ] Create your first `/start` morning command
- [ ] Set up Obsidian (already downloaded at `~/apps/obsidian/Obsidian.AppImage --no-sandbox`)
- [ ] Point Obsidian vault at `~/vault`

### Phase 3: Docker Stacks (next)
Spin up one at a time, test each before moving on:
- [ ] **Ollama** — local LLM, test it works, run a model
- [ ] **Open WebUI** — browser UI for Ollama
- [ ] **n8n** — automation workflows
- [ ] **Home Assistant** — home automation hub

### Phase 4: Life OS / Notion MCP
- [ ] Create Notion workspace with databases (tasks, fitness, budget, food)
- [ ] Connect Notion MCP to Claude Code
- [ ] Build and test pre-built prompts for each life area
- [ ] Find / recover your original ChatGPT work on this

### Phase 5: Home Automation Lab
- [ ] Map out your devices (lights, TV, aircon, blinds — brands/protocols)
- [ ] Configure Home Assistant integrations
- [ ] Connect Home Assistant to Claude Code via MCP
- [ ] Build automations and voice/chat control

### Phase 6: Revive Game Projects
- [ ] Pizzatorio — modular refactor + CLAUDE.md for agents
- [ ] Flax Spaceship Sim — fix Web Components issue
- [ ] Turn-based sci-fi mobile game — resume GDD and Phase 1

---

## 6. Immediate Next Actions (right now, in order)

```bash
# 1. Authenticate Claude Code
claude

# 2. Log out and back in (then open terminal again)

# 3. Verify Docker works without sudo
docker run hello-world

# 4. Open your vault in VS Code with Claude Code
code ~/vault
# then Ctrl+~ for terminal inside VS Code
cd ~/vault && claude

# 5. Run init
# type: /init
# then follow the prompts
```

---

## Quick Reference Card

```
Ctrl+Shift+C / V    Copy/paste in terminal
Ctrl+~              Open terminal inside VS Code
Ctrl+Shift+X        Extensions in VS Code
code ~/vault        Open vault in VS Code
cd ~/vault && claude  Start Claude Code assistant
docker compose up -d  Start a Docker stack
docker ps           See running containers
~/stacks/           Your Docker services live here
~/vault/            Your Claude Code brain lives here
~/projects/         Your code projects live here
```
