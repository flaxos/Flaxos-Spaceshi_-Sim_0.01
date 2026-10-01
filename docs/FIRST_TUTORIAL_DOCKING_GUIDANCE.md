# First tutorial docking guidance

`01_tutorial_intercept` (First Contact) uses the same Docking crew guide as
`07_docking_test`, under Mission → Objectives. The guide shows server-reported
Helm and Engineering coverage, existing controls, final docking limits and the
manual post-dock thrust cutoff. Its briefing, approach hint and completion text
repeat the relevant limits and cutoff instruction.

5 km is an approach milestone. Docking requires at most 50 m and 1 m/s relative
speed. After docking, manually set Helm thrust to zero and confirm actual output;
the station can constrain motion while drive and fuel use continue. CPU ASSIST
still requires approving the navigation program. Solo pilots explicitly release
and claim stations; Engineering CPU coverage is limited to heat sinks when fitted.

The tutorial's ships, objectives, hint triggers, progression and physics are
unchanged. This adds guidance to existing behavior. PR418 already supplied the
Docking Test's post-dock instruction; this change extends it to First Contact.
Power accounting and the original cooling policy from PR419 remain in place.

## Human verification

Use a separate clean checkout at the PR's reported head and start the current
Svelte stack with `python tools/start_gui_stack.py`. Leave an existing playtest
checkout and runtime alone. Launch “Tutorial: Intercept and Dock,” then:

1. Read Mission → Objectives and expand Full mission briefing. Check the
   approach milestone, 50 m / 1 m/s limits, explicit cutoff and CPU coverage.
2. Explicitly join Helm; use the detected Tycho contact, CPU ASSIST rendezvous
   approval and Nav Tools REQUEST DOCK. Check the original three objectives.
3. After actual docking, manually set the Manual Flight throttle to zero. Confirm
   actual output and fuel use, then check that the completion text also reminds
   you to cut thrust. Repeat with a companion on Engineering if available.

A short native-stack text/control smoke check is separate from completing this
flight. Owner human acceptance remains pending. The existing enemy-fire failure
and frontend fixture-cleanup race remain separately reported in the PR checks;
a passing retry does not resolve either baseline issue.
