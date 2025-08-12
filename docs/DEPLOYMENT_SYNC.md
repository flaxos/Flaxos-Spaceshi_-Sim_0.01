# Deployment & Release Sync (Sprint 2 → 3)

## Branching
- `main` — stable demos
- `s2-demo` — this drop (missiles/ECM/PD)
- `s3-attitude` — quaternion/RCS work

## Release Checklist
- [ ] Unit tests pass locally
- [ ] Manual demo: Interceptor fires, Target PDC engages
- [ ] `get_state` includes `missiles` (HUD verified)
- [ ] README, AI_INSTRUCTIONS, USER_GUIDE updated
- [ ] Tag release: `v0.2.0-sprint2`

## Roll-forward Plan
- Merge `s3-attitude` once HUD reads attitude cache and tests pass.
