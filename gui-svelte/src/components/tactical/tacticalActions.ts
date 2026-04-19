import { wsClient } from "../../lib/ws/wsClient.js";

export type TacticalWeaponType = "railgun" | "torpedo" | "missile" | "pdc";
export type MunitionType = "torpedo" | "missile";

export const GUIDANCE_OPTIONS = ["dumb", "guided", "smart"] as const;
export const WARHEAD_OPTIONS = ["fragmentation", "shaped_charge", "emp"] as const;
export const TORPEDO_PROFILE_OPTIONS = ["direct", "evasive"] as const;
export const MISSILE_PROFILE_OPTIONS = ["direct", "evasive", "terminal_pop", "bracket"] as const;

export function getMunitionProfileOptions(munitionType: MunitionType): readonly string[] {
  return munitionType === "torpedo" ? TORPEDO_PROFILE_OPTIONS : MISSILE_PROFILE_OPTIONS;
}

function withOptionalTarget(targetId?: string): Record<string, unknown> {
  return targetId ? { target: targetId } : {};
}

export async function lockTarget(contactId: string) {
  return wsClient.sendShipCommand("lock_target", { contact_id: contactId });
}

export async function unlockTarget() {
  return wsClient.sendShipCommand("unlock_target", {});
}

export async function toggleAutoTactical(enabled: boolean) {
  return wsClient.sendShipCommand(enabled ? "disable_auto_tactical" : "enable_auto_tactical", {});
}

export async function setEngagementRules(mode: string) {
  return wsClient.sendShipCommand("set_engagement_rules", { mode });
}

export async function toggleWeaponAuthorization(
  weaponType: TacticalWeaponType,
  enabled: boolean,
  options: { count?: number; profile?: string } = {},
) {
  const command = enabled ? "deauthorize_weapon" : "authorize_weapon";
  return wsClient.sendShipCommand(command, {
    weapon_type: weaponType,
    count: options.count ?? 1,
    profile: options.profile ?? "direct",
  });
}

export async function fireRailgun(options: {
  mountId?: string;
  targetId?: string;
  slugType?: string;
}) {
  const params: Record<string, unknown> = {
    ...withOptionalTarget(options.targetId),
  };

  if (options.mountId) params.mount_id = options.mountId;
  if (options.slugType) params.slug_type = options.slugType;

  return wsClient.sendShipCommand("fire_railgun", params);
}

export async function launchDirectMunition(
  munitionType: MunitionType,
  options: {
    targetId?: string;
    profile?: string;
    guidanceMode?: string;
    warheadType?: string;
  } = {},
) {
  const command = munitionType === "torpedo" ? "launch_torpedo" : "launch_missile";
  return wsClient.sendShipCommand(command, {
    ...withOptionalTarget(options.targetId),
    profile: options.profile ?? "direct",
    guidance_mode: options.guidanceMode,
    warhead_type: options.warheadType,
  });
}

export async function fireArcadeWeapon(
  weaponType: TacticalWeaponType,
  targetId?: string,
) {
  if (weaponType === "railgun") {
    return fireRailgun({ targetId });
  }
  if (weaponType === "pdc") {
    return firePdc({ targetId });
  }
  return launchDirectMunition(weaponType as MunitionType, { targetId, profile: "direct" });
}

export async function launchSalvo(options: {
  munitionType: MunitionType;
  count: number;
  targetId?: string;
  profile?: string;
  guidanceMode?: string;
  warheadType?: string;
}) {
  return wsClient.sendShipCommand("launch_salvo", {
    munition_type: options.munitionType,
    count: options.count,
    ...withOptionalTarget(options.targetId),
    profile: options.profile ?? "direct",
    guidance_mode: options.guidanceMode,
    warhead_type: options.warheadType,
  });
}

export async function programMunition(options: {
  munitionType: MunitionType;
  guidanceMode?: string;
  warheadType?: string;
  flightProfile?: string;
  pnGain?: number;
  fuseDistance?: number;
  terminalRange?: number;
  boostDuration?: number;
  datalink?: boolean;
}) {
  return wsClient.sendShipCommand("program_munition", {
    munition_type: options.munitionType,
    guidance_mode: options.guidanceMode,
    warhead_type: options.warheadType,
    flight_profile: options.flightProfile,
    pn_gain: options.pnGain,
    fuse_distance: options.fuseDistance,
    terminal_range: options.terminalRange,
    boost_duration: options.boostDuration,
    datalink: options.datalink,
  });
}

export async function setPdcMode(mode: string) {
  return wsClient.sendShipCommand("set_pdc_mode", { mode });
}

export async function setPdcPriority(torpedoIds: string[]) {
  return wsClient.sendShipCommand("set_pdc_priority", { torpedo_ids: torpedoIds });
}

export async function assignPdcTarget(mountId: string, contactId: string) {
  return wsClient.sendShipCommand("assign_pdc_target", {
    mount_id: mountId,
    contact_id: contactId,
  });
}

export async function addTrack(contactId: string) {
  return wsClient.sendShipCommand("add_track", { contact_id: contactId });
}

export async function removeTrack(contactId: string) {
  return wsClient.sendShipCommand("remove_track", { contact_id: contactId });
}

export async function firePdc(options: { mountId?: string; targetId?: string }) {
  return wsClient.sendShipCommand("fire_pdc", {
    weapon_id: options.mountId,
    ...withOptionalTarget(options.targetId),
  });
}
