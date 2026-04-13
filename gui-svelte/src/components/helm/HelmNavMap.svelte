<script lang="ts">
  import Panel from "../layout/Panel.svelte";
  import SpatialMapCanvas from "../spatial/SpatialMapCanvas.svelte";
  import type { SpatialLegendItem, SpatialLink, SpatialRing, SpatialTrack } from "../spatial/spatialMapTypes.js";
  import { gameState } from "../../lib/stores/gameState.js";
  import { selectedHelmTargetId } from "../../lib/stores/helmUi.js";
  import {
    asRecord,
    extractShipState,
    getAutopilotSnapshot,
    getContacts,
    getCourse,
    getDockingSnapshot,
    getOrientation,
    getPosition,
    getVelocity,
    getWaypoint,
    toStringValue,
    toVec3,
    type JsonMap,
    type Vec3,
  } from "./helmData.js";

  const LEGEND: SpatialLegendItem[] = [
    { label: "Own ship", color: "#8ef7ff", symbol: "▲" },
    { label: "Contact", color: "#82b8ff", symbol: "●" },
    { label: "Waypoint", color: "#ffd46b", symbol: "⊕" },
    { label: "Beacon", color: "#bfa9ff", symbol: "⊗" },
  ];

  const legendItems = LEGEND;

  $: ship = extractShipState($gameState);
  $: contacts = getContacts(ship);
  $: waypoint = getWaypoint(ship);
  $: shipPosition = getPosition(ship);
  $: shipVelocity = getVelocity(ship);
  $: shipHeading = getOrientation(ship).yaw;
  $: docking = getDockingSnapshot(ship);
  $: autopilot = getAutopilotSnapshot(ship);
  $: navPoints = deriveNavPoints(ship);
  $: contactTracks = contacts.map((contact) => ({
    id: contact.id,
    label: contact.id,
    position: contact.position,
    velocity: contact.velocity,
    kind: contact.id === docking.targetId ? "objective" : "neutral",
    annotation: `${contact.name} · ${contact.classification}`,
    selectable: true,
    elevationConnector: contact.id === docking.targetId || contact.id === $selectedHelmTargetId ? "selected" : "none",
  } satisfies SpatialTrack));

  $: waypointTrack = waypoint
    ? ({
        id: "helm-waypoint",
        label: "WAYPOINT",
        position: waypoint,
        kind: "waypoint",
        annotation: autopilot.program ? `AP ${autopilot.program.replaceAll("_", " ").toUpperCase()}` : "Course target",
        selectable: false,
        elevationConnector: "always",
        elevationLabel: "WAYPOINT",
      } satisfies SpatialTrack)
    : null;

  $: beaconTracks = navPoints.map((point, index) => ({
    id: `nav-point:${index}`,
    label: `NAV ${index + 1}`,
    position: point,
    kind: "beacon",
    annotation: "Route / beacon",
    selectable: false,
    elevationConnector: index === 0 ? "selected" : "none",
    elevationLabel: `NAV ${index + 1}`,
  } satisfies SpatialTrack));

  $: tracks = [
    {
      id: "ownship",
      label: toStringValue(ship.name, toStringValue(ship.id, "OWN SHIP")),
      position: shipPosition,
      velocity: shipVelocity,
      headingDeg: shipHeading,
      kind: "ownship",
      selectable: false,
      annotation: autopilot.active ? "Autopilot engaged" : "Manual flight",
      emphasis: true,
      elevationConnector: "always",
      elevationLabel: "OWN SHIP",
    } satisfies SpatialTrack,
    ...contactTracks,
    ...(waypointTrack ? [waypointTrack] : []),
    ...beaconTracks,
  ];

  $: waypointOrBeaconId = waypointTrack?.id ?? beaconTracks[0]?.id ?? "";
  $: objectiveId = waypointOrBeaconId || docking.targetId || "";
  $: dockingTarget = contacts.find((contact) => contact.id === docking.targetId) ?? null;
  $: rings = dockingTarget && docking.dockingRange > 0
    ? [{
        id: "docking-ring",
        center: dockingTarget.position,
        radius: docking.dockingRange,
        color: "rgba(255, 212, 107, 0.32)",
        label: "Docking",
        dashed: true,
      } satisfies SpatialRing]
    : [];
  $: links = buildLinks(shipPosition, waypoint, navPoints, dockingTarget?.position ?? null);
  $: initialRadius = deriveInitialRadius(contacts, waypoint, navPoints, dockingTarget?.position ?? null);

  function deriveNavPoints(currentShip: JsonMap): Vec3[] {
    const course = getCourse(currentShip);
    const directCandidates = [
      currentShip.waypoints,
      asRecord(currentShip.navigation)?.waypoints,
      course.waypoints,
      asRecord(currentShip.course_plot)?.waypoints,
      asRecord(currentShip.flight_computer)?.waypoints,
      asRecord(asRecord(currentShip.course_plot)?.plot)?.points,
    ];

    for (const candidate of directCandidates) {
      if (Array.isArray(candidate)) {
        return candidate
          .map((item) => asRecord(item) ?? (Array.isArray(item) ? { x: item[0], y: item[1], z: item[2] } : null))
          .filter((item): item is JsonMap => Boolean(item))
          .map((item) => toVec3(item));
      }
    }

    return [];
  }

  function buildLinks(position: Vec3, activeWaypoint: Vec3 | null, points: Vec3[], dockingPosition: Vec3 | null): SpatialLink[] {
    const result: SpatialLink[] = [];
    const autopilotLabel = autopilot.active
      ? `AP ${autopilot.program ? autopilot.program.replaceAll("_", " ").toUpperCase() : "PATH"}`
      : "Course";

    if (points.length > 0) {
      result.push({
        id: "route-entry",
        from: position,
        to: points[0],
        color: autopilot.active ? "rgba(191, 169, 255, 0.62)" : "rgba(191, 169, 255, 0.45)",
        dashed: true,
        label: autopilot.active ? autopilotLabel : "Route",
        arrow: true,
      });
      for (let index = 1; index < points.length; index += 1) {
        result.push({
          id: `route:${index}`,
          from: points[index - 1],
          to: points[index],
          color: autopilot.active ? "rgba(191, 169, 255, 0.44)" : "rgba(191, 169, 255, 0.28)",
          dashed: true,
          faint: true,
          arrow: true,
        });
      }
    } else if (activeWaypoint) {
      result.push({
        id: "active-course",
        from: position,
        to: activeWaypoint,
        color: autopilot.active ? "rgba(255, 212, 107, 0.6)" : "rgba(255, 212, 107, 0.45)",
        dashed: true,
        label: autopilot.active ? autopilotLabel : "Course",
        arrow: true,
      });
    }

    if (dockingPosition) {
      result.push({
        id: "docking-corridor",
        from: position,
        to: dockingPosition,
        color: "rgba(109, 219, 255, 0.4)",
        label: autopilot.active ? "Docking AP" : "Docking",
        arrow: true,
      });
    }

    return result;
  }

  function deriveInitialRadius(currentContacts: typeof contacts, activeWaypoint: Vec3 | null, points: Vec3[], dockingPosition: Vec3 | null) {
    const distances = currentContacts.map((contact) => contact.distance);
    if (activeWaypoint) distances.push(distanceBetween(shipPosition, activeWaypoint));
    for (const point of points) distances.push(distanceBetween(shipPosition, point));
    if (dockingPosition) distances.push(distanceBetween(shipPosition, dockingPosition));
    return Math.max(12_000, Math.min(400_000, (Math.max(...distances, 25_000) || 25_000) * 1.1));
  }

  function distanceBetween(a: Vec3, b: Vec3) {
    return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
  }
</script>

<Panel title="Nav Map" domain="helm" priority="primary" className="helm-nav-map-panel">
  <SpatialMapCanvas
    mode="helm"
    {tracks}
    {rings}
    {links}
    {legendItems}
    ownshipId="ownship"
    selectedId={$selectedHelmTargetId}
    {objectiveId}
    {initialRadius}
    caption="Helm centers on route geometry: own ship heading, AP route / course path, nav beacons, selected contacts, and docking corridors. Elevation markers stay focused instead of drawing a connector for every track."
    on:select={(event) => selectedHelmTargetId.set(event.detail.id)}
  />
</Panel>
