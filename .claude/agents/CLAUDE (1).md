# CLAUDE.md — Homelab Project Instructions

## Who I Am
Flax. Customer Solutions Manager, not an engineer. Self-taught tech hobbyist returning to home labbing after ~10 years. I understand systems thinking and process improvement but I'm learning infrastructure patterns as I go. Explain decisions, don't just execute them.

## Project Structure
```
~/homelab/
├── CLAUDE.md              # You're reading this
├── current-state.md       # Living doc: what's running, specs, network info
├── ROADMAP.md             # The phased plan (Phase 0-5)
├── management/            # Dozzle, Portainer/Komodo, Watchtower
│   └── docker-compose.yml
├── dashboard/             # Homepage
│   └── docker-compose.yml
├── traefik/               # Reverse proxy
│   └── docker-compose.yml
├── dns/                   # Pi-hole or AdGuard Home
│   └── docker-compose.yml
├── vpn/                   # WireGuard (wg-easy)
│   └── docker-compose.yml
├── ai/                    # Ollama, Open WebUI, AnythingLLM
│   └── docker-compose.yml
├── automation/            # n8n
│   └── docker-compose.yml
└── .env.example           # Template for secrets (actual .env is gitignored)
```

## Critical Rules

### DO
- Read `current-state.md` before making changes
- Check disk space (`df -h`) before pulling images or models
- Use Docker Compose for everything — one `docker-compose.yml` per service group
- Put all compose files under `~/homelab/` in the correct subdirectory
- Use `.env` files for secrets, never hardcode passwords
- Git commit after each successful change with a clear message
- Test new services alongside existing ones before cutting over
- Update `current-state.md` after completing any change
- Use the shared Docker network `lab` for inter-service communication
- Explain what you're doing and why in plain language

### DON'T
- Never modify a running service's config without a rollback plan
- Never use bare `docker run` — always compose
- Never commit `.env` files or secrets to git
- Never expose services directly to the internet without Traefik + auth
- Never assume what's running — always check first
- Never pull large Docker images or AI models without checking available disk
- Don't over-engineer — if it works and Flax understands it, it's good enough
- Don't skip the "why" — always explain the reasoning behind choices

## Docker Conventions
- Network: all services join `lab` network unless they need isolation
- Naming: container names match their service group (e.g., `traefik`, `ollama`, `homepage`)
- Restart policy: `unless-stopped` for production services, `no` for experiments
- Volumes: named volumes preferred over bind mounts for data persistence
- Logging: use `json-file` driver with max-size limits to prevent disk fill

## Git Conventions
- Commit messages: `[phase] brief description` (e.g., `[p1] add dozzle and portainer compose`)
- Branch: `main` for working config, feature branches for experiments
- Tag phases when complete: `v0.1-phase1`, `v0.2-phase2`, etc.

## Current Phase
Check ROADMAP.md for the active phase. Start each session by asking Flax what they want to work on, then reference the roadmap to see where it fits.
