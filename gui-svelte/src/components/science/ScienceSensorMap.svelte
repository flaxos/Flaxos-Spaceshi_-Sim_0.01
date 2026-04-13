<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import SpatialMapCanvas from "../spatial/SpatialMapCanvas.svelte";
  import type { SpatialLegendItem, SpatialLink, SpatialRing, SpatialTrack } from "../spatial/spatialMapTypes.js";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedScienceContactId } from "../../lib/stores/scienceUi.js";
  import { getOrientation, getPosition, getVelocity, toStringValue } from "../helm/helmData.js";
  import {
    currentNoiseFloor,
    formatWatts,
    getScienceContacts,
    getScienceShip,
  } from "./scienceData.js";

  const LEGEND: SpatialLegendItem[] = [
    { label: "Own ship", color: "#8ef7ff", symbol: "▲" },
    { label: "Resolved contact", color: "#82b8ff", symbol: "●" },
    { label: "Ghost / low confidence", color: "#61d8ff", symbol: "◌" },
  ];

  const legendItems = LEGEND;

  $: ship = getScienceShip($gameState);
  $: contacts = getScienceContacts(ship);
  $: shipPosition = getPosition(ship);
  $: shipVelocity = getVelocity(ship);
  $: shipHeading = getOrientation(ship).yaw;
  $: noiseFloor = currentNoiseFloor(ship);
  $: tracks = [
    {
      id: "ownship",
      label: toStringValue(ship.name, toStringValue(ship.id, "OWN SHIP")),
      position: shipPosition,
      velocity: shipVelocity,
      headingDeg: shipHeading,
      kind: "ownship",
      selectable: false,
      annotation: `Noise floor ${formatWatts(noiseFloor)}`,
      emphasis: true,
      elevationConnector: "always",
      elevationLabel: "OWN SHIP",
    } satisfies SpatialTrack,
    ...contacts.map((contact) => ({
      id: contact.id,
      label: contact.id,
      position: contact.position,
      velocity: contact.velocity,
      kind: contact.confidence < 0.75 ? "ghost" : "neutral",
      confidence: contact.confidence,
      annotation: `${contact.detectionMethod} · ${Math.round(contact.confidence * 100)}%`,
      selectable: true,
      elevationConnector: contact.id === $selectedScienceContactId ? "selected" : "none",
    } satisfies SpatialTrack)),
  ];

  $: selectedContact = contacts.find((contact) => contact.id === $selectedScienceContactId) ?? null;
  $: rings = buildSweepRings();
  $: links = selectedContact
    ? [{
        id: "science-focus",
        from: shipPosition,
        to: selectedContact.position,
        color: "rgba(97, 216, 255, 0.36)",
        dashed: true,
        label: "Passive track",
        arrow: true,
      } satisfies SpatialLink]
    : [];
  $: initialRadius = Math.max(15_000, Math.min(400_000, contacts.reduce((max, contact) => Math.max(max, contact.distance), 40_000) * 1.15));

  function buildSweepRings(): SpatialRing[] {
    const farthest = contacts.reduce((max, contact) => Math.max(max, contact.distance), 30_000);
    return [0.3, 0.6, 1].map((ratio, index) => ({
      id: `science-sweep:${index}`,
      center: shipPosition,
      radius: farthest * ratio,
      color: `rgba(97, 216, 255, ${0.18 - index * 0.03})`,
      dashed: true,
      label: index === 2 ? "Passive sweep" : undefined,
    }));
  }
</script>

<Panel title="Sensor Picture" domain="sensor" priority="primary" className="science-sensor-map-panel">
  <SpatialMapCanvas
    mode="science"
    {tracks}
    {rings}
    {links}
    {legendItems}
    ownshipId="ownship"
    selectedId={$selectedScienceContactId}
    {initialRadius}
    caption={`Science keeps the passive picture readable: uncertainty halos stay in plan view while the elevation strip only highlights own ship and the focused contact. Current own-ship noise floor ${formatWatts(noiseFloor)}.`}
    on:select={(event) => selectedScienceContactId.set(event.detail.id)}
  />
</Panel>
