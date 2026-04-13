<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import SpatialMapCanvas from "../spatial/SpatialMapCanvas.svelte";
  import type { SpatialLegendItem, SpatialLink, SpatialRing, SpatialTrack } from "../spatial/spatialMapTypes.js";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedTacticalTargetId } from "../../lib/stores/tacticalUi.js";
  import { extractShipState, getTacticalContacts, getWeaponMounts } from "./tacticalData.js";
  import { lockTarget } from "./tacticalActions.js";
  import { getOrientation, getPosition, getVelocity, toStringValue, toVec3 } from "../helm/helmData.js";

  type CombatEntity = Record<string, unknown>;

  const LEGEND: SpatialLegendItem[] = [
    { label: "Own ship", color: "#8ef7ff", symbol: "▲" },
    { label: "Threat", color: "#ff5a5a", symbol: "◆" },
    { label: "Neutral", color: "#82b8ff", symbol: "●" },
    { label: "Rail slug", color: "#f9f871", symbol: "•" },
    { label: "Munition", color: "#ff9966", symbol: "◇" },
  ];
  const legendItems = LEGEND;

  let lockBusy = false;

  $: ship = extractShipState($gameState);
  $: contacts = getTacticalContacts(ship);
  $: mounts = getWeaponMounts(ship);
  $: shipPosition = getPosition(ship);
  $: shipVelocity = getVelocity(ship);
  $: shipHeading = getOrientation(ship).yaw;
  $: projectiles = Array.isArray(($gameState as Record<string, unknown>).projectiles) ? (($gameState as Record<string, unknown>).projectiles as CombatEntity[]) : [];
  $: torpedoes = Array.isArray(($gameState as Record<string, unknown>).torpedoes) ? (($gameState as Record<string, unknown>).torpedoes as CombatEntity[]) : [];

  $: contactTracks = contacts.map((contact) => ({
    id: contact.id,
    label: contact.id,
    position: contact.position,
    velocity: contact.velocity,
    kind: contact.diplomaticState.toLowerCase().includes("hostile") || contact.threatLevel === "red" || contact.threatLevel === "orange"
      ? "hostile"
      : "neutral",
    confidence: contact.confidence,
    annotation: `${contact.classification} · ${Math.round(contact.distance / 1000)} km`,
    selectable: true,
    elevationConnector: contact.id === $selectedTacticalTargetId ? "selected" : "none",
  } satisfies SpatialTrack));

  $: projectileTracks = projectiles
    .map((entity) => {
      const position = toVec3(entity.position);
      const velocity = toVec3(entity.velocity);
      return {
        id: `proj:${toStringValue(entity.id, Math.random().toString(36).slice(2))}`,
        label: toStringValue(entity.mount, toStringValue(entity.weapon, "slug")).toUpperCase(),
        position,
        velocity,
        kind: "projectile",
        annotation: toStringValue(entity.target),
        selectable: false,
        elevationConnector: "none",
      } satisfies SpatialTrack;
    });

  $: munitionTracks = torpedoes
    .map((entity) => {
      const kind = toStringValue(entity.munition_type, "torpedo");
      const target = toStringValue(entity.target);
      return {
        id: `mun:${toStringValue(entity.id, Math.random().toString(36).slice(2))}`,
        label: toStringValue(entity.id, kind.toUpperCase()),
        position: toVec3(entity.position),
        velocity: toVec3(entity.velocity),
        kind: "munition",
        annotation: `${kind.toUpperCase()}${target ? ` → ${target}` : ""}`,
        selectable: false,
        elevationConnector: "none",
      } satisfies SpatialTrack;
    });

  $: tracks = [
    {
      id: "ownship",
      label: toStringValue(ship.name, toStringValue(ship.id, "OWN SHIP")),
      position: shipPosition,
      velocity: shipVelocity,
      headingDeg: shipHeading,
      kind: "ownship",
      selectable: false,
      emphasis: true,
      annotation: "Combat platform",
      elevationConnector: "always",
      elevationLabel: "OWN SHIP",
    } satisfies SpatialTrack,
    ...contactTracks,
    ...munitionTracks,
    ...projectileTracks,
  ];

  $: selectedContact = contacts.find((contact) => contact.id === $selectedTacticalTargetId) ?? null;

  $: rings = buildRings(shipPosition, mounts);
  $: links = buildLinks(shipPosition, selectedContact, torpedoes, contacts);
  $: initialRadius = deriveInitialRadius(contacts, mounts);

  function buildRings(position: typeof shipPosition, weaponMounts: typeof mounts): SpatialRing[] {
    const grouped = new Map<string, number>();
    for (const mount of weaponMounts) {
      if (!mount.range || mount.range <= 0) continue;
      const key = mount.weaponType;
      grouped.set(key, Math.max(grouped.get(key) ?? 0, mount.range));
    }

    const palette: Record<string, { color: string; label: string }> = {
      railgun: { color: "rgba(135, 196, 255, 0.34)", label: "Rail" },
      pdc: { color: "rgba(98, 255, 201, 0.28)", label: "PDC" },
      torpedo: { color: "rgba(255, 173, 91, 0.28)", label: "Torp" },
      missile: { color: "rgba(255, 123, 123, 0.26)", label: "Missile" },
      other: { color: "rgba(220, 220, 220, 0.2)", label: "Envelope" },
    };

    return Array.from(grouped.entries()).map(([weaponType, radius]) => ({
      id: `ring:${weaponType}`,
      center: position,
      radius,
      color: palette[weaponType]?.color ?? palette.other.color,
      label: palette[weaponType]?.label ?? palette.other.label,
      dashed: weaponType !== "railgun",
    }));
  }

  function buildLinks(
    position: typeof shipPosition,
    selected: typeof selectedContact,
    munitions: CombatEntity[],
    tacticalContacts: typeof contacts,
  ): SpatialLink[] {
    const result: SpatialLink[] = [];
    if (selected) {
      result.push({
        id: "selected-track",
        from: position,
        to: selected.position,
        color: "rgba(255, 90, 90, 0.6)",
        label: "Current target",
        arrow: true,
      });
    }

    for (const munition of munitions) {
      const targetId = toStringValue(munition.target);
      const target = tacticalContacts.find((contact) => contact.id === targetId);
      if (!target) continue;
      result.push({
        id: `munition:${toStringValue(munition.id, targetId)}`,
        from: toVec3(munition.position),
        to: target.position,
        color: "rgba(255, 166, 102, 0.34)",
        dashed: true,
        faint: true,
        arrow: true,
      });
    }
    return result;
  }

  function deriveInitialRadius(tacticalContacts: typeof contacts, weaponMounts: typeof mounts) {
    const farthestContact = tacticalContacts.reduce((max, contact) => Math.max(max, contact.distance), 0);
    const farthestRange = weaponMounts.reduce((max, mount) => Math.max(max, mount.range || 0), 0);
    return Math.max(15_000, Math.min(500_000, Math.max(farthestContact, farthestRange) * 1.1 || 40_000));
  }

  async function lockSelected(id = $selectedTacticalTargetId) {
    if (!id) return;
    lockBusy = true;
    try {
      selectedTacticalTargetId.set(id);
      await lockTarget(id);
    } finally {
      lockBusy = false;
    }
  }
</script>

<Panel title="Tactical Map" domain="sensor" priority="primary" className="tactical-map-panel">
  <SpatialMapCanvas
    mode="tactical"
    {tracks}
    {rings}
    {links}
    {legendItems}
    ownshipId="ownship"
    selectedId={$selectedTacticalTargetId}
    {initialRadius}
    caption="Plan view emphasizes target geometry and weapon envelopes. The elevation strip now only mirrors ownship and focused tracks so Z cues stay readable. Wheel zooms on cursor; drag pans."
    selectionActionLabel="Lock"
    selectionActionDisabled={!$selectedTacticalTargetId || lockBusy}
    on:select={(event) => selectedTacticalTargetId.set(event.detail.id)}
    on:activate={(event) => lockSelected(event.detail.id)}
  />
</Panel>
