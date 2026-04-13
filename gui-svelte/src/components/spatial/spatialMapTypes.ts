import type { Vec3 } from "../helm/helmData.js";

export type SpatialMapMode = "tactical" | "helm" | "science";

export type SpatialTrackKind =
  | "ownship"
  | "friendly"
  | "neutral"
  | "hostile"
  | "waypoint"
  | "objective"
  | "beacon"
  | "ghost"
  | "projectile"
  | "munition";

export interface SpatialTrack {
  id: string;
  label: string;
  position: Vec3;
  velocity?: Vec3;
  kind: SpatialTrackKind;
  headingDeg?: number;
  confidence?: number;
  annotation?: string;
  active?: boolean;
  selectable?: boolean;
  emphasis?: boolean;
  elevationConnector?: "auto" | "always" | "selected" | "none";
  elevationLabel?: string;
}

export interface SpatialRing {
  id: string;
  radius: number;
  color: string;
  label?: string;
  dashed?: boolean;
  center?: Vec3;
}

export interface SpatialLink {
  id: string;
  from: Vec3;
  to: Vec3;
  color: string;
  label?: string;
  dashed?: boolean;
  faint?: boolean;
  arrow?: boolean;
}

export interface SpatialLegendItem {
  label: string;
  color: string;
  symbol?: string;
}
