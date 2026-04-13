# Agent Teams Prompt: Spaceship Sim Polish & Feature Sprint

> Historical helper: this prompt predates the current Svelte-first UAT/documentation flow.
> Keep it for reference only. For current repo guidance, prefer `AGENTS.md`, `README.md`, `docs/README.md`, and `prompts/UAT_REFACTOR_AUDIT_PROMPT.txt`.

## HOW TO USE THIS FILE

### Prerequisites
1. Make sure Claude Code is installed and updated (`claude --version`)
2. Enable Agent Teams (it's experimental):
   ```bash
   export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
   ```
3. Place the CLAUDE.md file in your project root
4. Navigate to your project directory:
   ```bash
   cd ~/Flaxos-Spaceshi_-Sim_0.01
   ```
5. Start Claude Code:
   ```bash
   claude
   ```
6. Paste the prompt below (everything between the --- lines)

### What Will Happen
- Claude Code becomes the "team lead"
- It will read the codebase, create a plan, then spawn teammates
- Each teammate works in their own context on their assigned scope
- They communicate through a shared task list and direct messages
- You can watch progress, interact with individual teammates, or let it run
- When done, review the changes before committing

### Important Notes
- This is TOKEN INTENSIVE — it will burn through Max plan usage faster than normal
- Start with the SMALL prompt first to test the workflow
- Review all changes before accepting — agents can and will make mistakes
- You are the tech lead, not a passive observer. Check in on progress.

---

## PROMPT: SMALL (Start Here — Single Feature Polish)

Use this first to test the workflow before going big.

```
Read the entire codebase and understand the current state of the project.
Then create an agent team with TWO teammates to work on the following:

TEAMMATE 1 — "Combat Polish":
- Review the combat system implementation (weapons, targeting, damage)
- Compare what's implemented vs the design spec in CLAUDE.md
- Fix any bugs or incomplete implementations
- Ensure railgun and PDC mechanics match the design tables
- Verify the targeting pipeline works: contact → track → lock → solution → fire
- Add missing type hints and docstrings to combat-related code

TEAMMATE 2 — "Test & Document":
- Wait for Combat Polish to report initial findings before starting
- Write unit tests for the combat system (weapon firing, damage calculation, targeting)
- Write a brief COMBAT-STATUS.md documenting: what works, what's broken, what's missing
- Run the tests and report results

Coordinate the team. When both are done, synthesize their findings into a
summary for me to review. Do NOT commit anything — I want to review first.
```

---

## PROMPT: MEDIUM (Multi-Feature Sprint)

Use this once you're comfortable with how Agent Teams works.

```
Read the entire codebase. Assess the current state of every module.
Create a development plan, then spawn an agent team with THREE teammates:

TEAMMATE 1 — "Code Quality & Refactor":
Scope: Architecture and code health
- Map the full project structure and identify any monolithic files (300+ lines)
- Refactor large files into logical modules (but DON'T break imports)
- Add type hints to all function signatures
- Add docstrings to all classes and public methods
- Fix any obvious bugs you find during review
- Ensure server/main.py still starts cleanly after all changes

TEAMMATE 2 — "Feature: Combat Loop":
Scope: Implementing or completing the combat system
- Implement any missing pieces from the combat design:
  - Railgun: projectile travel time, hit calculation based on range + target accel
  - PDC: auto-turret tracking within gimbal limits, burst fire mechanics
  - Targeting pipeline: contact → track → lock → firing solution
  - Subsystem damage: impairment cascading (sensors down = degraded tracking)
  - Intercept scenario: player corvette vs fleeing freighter
- Coordinate with Teammate 1 if refactoring affects combat modules
- Write clear comments explaining physics/game logic decisions

TEAMMATE 3 — "QA & Documentation":
Scope: Testing and documentation
- Write unit tests for:
  - Weapon mechanics (fire rate, ammo, damage)
  - Targeting (solution confidence, range effects)
  - Subsystem damage cascading
  - Ship physics (acceleration, velocity, position updates)
- Write integration tests for the Intercept scenario flow
- Create/update these docs:
  - README.md (how to install, run, and play)
  - ARCHITECTURE.md (module map, data flow, key design decisions)
  - CHANGELOG.md (what changed in this sprint)
- Run all tests and report pass/fail

COORDINATION RULES:
- Teammate 1 goes first (15 min head start) so refactoring is done before others build on it
- Teammate 2 checks in with Teammate 1 before modifying shared modules
- Teammate 3 writes tests against the ACTUAL code, not assumptions
- All teammates: if you find a design question with no clear answer, flag it for me — don't guess

When all teammates report done, give me:
1. Summary of all changes
2. Test results
3. Any design questions or conflicts that need my input
4. A recommended commit plan (what to commit in what order)

Do NOT auto-commit. I review everything.
```

---

## PROMPT: LARGE (Full Sprint — Only When Confident)

This is the "make it better and ship me the next version" prompt.
Only use this once you've run the small and medium prompts successfully.

```
You are the tech lead for Flaxos Spaceship Sim. Read the full codebase,
read CLAUDE.md for design context, and assess the project state.

Create a sprint plan, then execute it with a full agent team (up to 4 teammates):

TEAMMATE 1 — "Architect":
- Full codebase audit: structure, dependencies, dead code, monolithic files
- Refactor into clean modular architecture if needed
- Ensure separation: server logic / game logic / network / GUI are independent
- Set up or improve project config: requirements.txt, .gitignore, pyproject.toml
- Performance check: anything obviously slow or wasteful?

TEAMMATE 2 — "Combat Engineer":
- Implement the full combat loop per CLAUDE.md design spec
- Weapons: railgun + PDC with all specified properties
- Targeting: full pipeline with confidence scoring
- Damage: subsystem model with cascading impairment
- Intercept scenario: fully playable from start to win/lose condition
- Ship AI: fleeing freighter behavior (flee + defensive PDC)
- Coordinate with Architect on module boundaries

TEAMMATE 3 — "QA Lead":
- Comprehensive test suite:
  - Unit tests for every game mechanic
  - Integration tests for scenario flow
  - Edge cases: zero ammo, all subsystems destroyed, point-blank range
- Run all tests, report coverage
- Manual test checklist for the Intercept scenario
- Bug report for anything that fails

TEAMMATE 4 — "Tech Writer":
- README.md: full project overview, install, run, play instructions
- ARCHITECTURE.md: module map, data flow diagrams (ASCII), design decisions
- COMBAT-GUIDE.md: player-facing explanation of mechanics
- CHANGELOG.md: all changes this sprint
- Update any existing docs that are outdated
- Review code comments for accuracy

SPRINT RULES:
- Architect gets a head start — others wait for structural changes to land
- Combat Engineer coordinates with Architect on module boundaries
- QA Lead tests against actual implemented code, not design docs
- Tech Writer documents what EXISTS, not what's planned
- All agents: flag design ambiguities for Flax, don't make assumptions
- All agents: check your work compiles/runs before reporting done

DELIVERABLES:
1. Sprint summary with all changes listed
2. Full test results with pass/fail counts
3. Design decisions log (what choices were made and why)
4. Open questions for Flax (anything that needs human judgment)
5. Recommended git commit sequence
6. Known issues / tech debt for next sprint

Do NOT auto-commit. Flax reviews and approves all changes.
```

---

## TIPS FOR RUNNING AGENT TEAMS

1. **Start with the SMALL prompt.** Seriously. Get a feel for the workflow first.

2. **Watch the token usage.** Agent Teams spawns multiple context windows.
   Each teammate burns tokens independently. A large prompt might use
   10-20x what a normal session would.

3. **You can talk to individual teammates.** If one is stuck or going in
   the wrong direction, intervene directly.

4. **The lead agent coordinates.** If teammates conflict (both editing the
   same file), the lead should catch it. If it doesn't, step in.

5. **Review EVERYTHING.** These agents will make confident mistakes.
   Your job is to catch them. Use `git diff` before committing.

6. **Commit incrementally.** Don't accept one massive commit.
   Review and commit each logical change separately.

7. **If it gets messy, start a new session.** Agent Teams is experimental.
   Sometimes the best move is: stop, review what was produced, cherry-pick
   the good stuff, and start fresh.
