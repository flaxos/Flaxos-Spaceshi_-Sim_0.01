# Lobby occupancy refresh

The visible Fleet Lobby refreshes `list_ships` and each ship's `station_status`
automatically, two seconds after the previous batch finishes. Manual **Refresh**
uses the same refresh chain. A batch publishes only after all its station reads
finish; failed or malformed reads show occupancy as unavailable rather than
offering seats as vacant.

Refresh stops when leaving the lobby, switching away from Mission, hiding the
browser document, losing the connection/registration, or unmounting the loader
(for example, collapsing its panel). Returning to a connected, visible lobby
refreshes immediately. Retired replies cannot replace the current snapshot or
start another timer. Mission labels use the existing shared mission store, so
occupancy refresh does not consume telemetry deltas.

Station claims and permissions remain server-authoritative. An occupied card is
a recent observation; a competing claim still requires server approval. Refresh
does not assign a ship, claim/reclaim a station, or bypass explicit rejoin.

## Human verification

Use the current build on an isolated test stack and two separate browser
profiles/contexts. The existing shared-ship playtest remains applicable.

1. Load an existing mission in B. Keep A unassigned and open **JOIN GAME** so A
   observes the Fleet Lobby. Claim Helm in B. A should show the actual occupied
   seat/player within a few seconds without clicking Refresh.
2. Release B's seat through the header, then explicitly join Engineering. A
   should show Helm vacant and Engineering occupied. Manual **Refresh** should
   still produce the same authoritative result.
3. Interrupt B's connection. A should see the old seat become vacant after the
   server releases it. After reconnecting, B must explicitly choose **Rejoin
   crew** and a station; no automatic claim should occur.
4. Leave A's lobby with **BACK**, or hide the document. Change B's seat, then
   return A to the lobby. Its first refresh should show the current occupancy.
   In a claimed profile, switching away from Mission or collapsing the loader
   should also stop its occupancy refresh until it is visible again.
5. Confirm an unclaimed observer still has no ship-command authority. If a
   lobby read fails, expect **Occupancy unavailable**, with no invented vacant
   buttons. Human acceptance is separate from automated checks.
