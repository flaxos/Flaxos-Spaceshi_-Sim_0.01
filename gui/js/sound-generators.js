/**
 * Procedural Sound Generators
 * All sounds synthesized via Web Audio API — no external audio files.
 * Each function takes an AudioContext and a destination GainNode,
 * creates short-lived audio graph nodes, and schedules them to play.
 */

// -- Utility: create a buffer filled with white noise --
function createNoiseBuffer(ctx, durationSec) {
  const length = Math.floor(ctx.sampleRate * durationSec);
  const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < length; i++) {
    data[i] = Math.random() * 2 - 1;
  }
  return buffer;
}

// ============================================================
// WEAPON SOUNDS
// ============================================================

/**
 * Railgun fire — sharp filtered noise burst with low-frequency thump.
 */
export function playRailgunFire(ctx, dest) {
  const now = ctx.currentTime;

  // High-frequency noise burst (bandpass 2kHz)
  const noiseBuffer = createNoiseBuffer(ctx, 0.15);
  const noise = ctx.createBufferSource();
  noise.buffer = noiseBuffer;

  const bp = ctx.createBiquadFilter();
  bp.type = "bandpass";
  bp.frequency.value = 2000;
  bp.Q.value = 2;

  const env = ctx.createGain();
  env.gain.setValueAtTime(0, now);
  env.gain.linearRampToValueAtTime(0.25, now + 0.005);
  env.gain.exponentialRampToValueAtTime(0.001, now + 0.1);

  noise.connect(bp).connect(env).connect(dest);
  noise.start(now);
  noise.stop(now + 0.15);

  // Low thump underneath (60Hz sine)
  const thump = ctx.createOscillator();
  thump.type = "sine";
  thump.frequency.value = 60;

  const thumpEnv = ctx.createGain();
  thumpEnv.gain.setValueAtTime(0, now);
  thumpEnv.gain.linearRampToValueAtTime(0.15, now + 0.003);
  thumpEnv.gain.exponentialRampToValueAtTime(0.001, now + 0.08);

  thump.connect(thumpEnv).connect(dest);
  thump.start(now);
  thump.stop(now + 0.1);
}

/**
 * PDC burst — rapid clicking noise, 3-5 short bursts at 50ms intervals.
 */
export function playPDCBurst(ctx, dest) {
  const now = ctx.currentTime;
  const burstCount = 3 + Math.floor(Math.random() * 3); // 3-5

  for (let i = 0; i < burstCount; i++) {
    const t = now + i * 0.05;
    const buf = createNoiseBuffer(ctx, 0.012);
    const src = ctx.createBufferSource();
    src.buffer = buf;

    const hp = ctx.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.value = 3000;

    const env = ctx.createGain();
    env.gain.setValueAtTime(0, t);
    env.gain.linearRampToValueAtTime(0.18, t + 0.001);
    env.gain.exponentialRampToValueAtTime(0.001, t + 0.01);

    src.connect(hp).connect(env).connect(dest);
    src.start(t);
    src.stop(t + 0.012);
  }
}

/**
 * Torpedo launch — low rumble, brown noise through lowpass.
 */
export function playTorpedoLaunch(ctx, dest) {
  const now = ctx.currentTime;
  const duration = 0.85;
  const buf = createNoiseBuffer(ctx, duration);
  const src = ctx.createBufferSource();
  src.buffer = buf;

  const lp = ctx.createBiquadFilter();
  lp.type = "lowpass";
  lp.frequency.value = 200;
  lp.Q.value = 1;

  const env = ctx.createGain();
  env.gain.setValueAtTime(0, now);
  env.gain.linearRampToValueAtTime(0.2, now + 0.05);
  env.gain.setValueAtTime(0.2, now + 0.55);
  env.gain.exponentialRampToValueAtTime(0.001, now + duration);

  src.connect(lp).connect(env).connect(dest);
  src.start(now);
  src.stop(now + duration);
}

/**
 * Missile launch — higher pitched version of torpedo launch.
 */
export function playMissileLaunch(ctx, dest) {
  const now = ctx.currentTime;
  const duration = 0.5;
  const buf = createNoiseBuffer(ctx, duration);
  const src = ctx.createBufferSource();
  src.buffer = buf;

  const bp = ctx.createBiquadFilter();
  bp.type = "bandpass";
  bp.frequency.value = 400;
  bp.Q.value = 1.5;

  const env = ctx.createGain();
  env.gain.setValueAtTime(0, now);
  env.gain.linearRampToValueAtTime(0.18, now + 0.03);
  env.gain.setValueAtTime(0.18, now + 0.25);
  env.gain.exponentialRampToValueAtTime(0.001, now + duration);

  src.connect(bp).connect(env).connect(dest);
  src.start(now);
  src.stop(now + duration);
}

// ============================================================
// IMPACT SOUNDS
// ============================================================

/**
 * Hull hit — deep sine thump with pitch drop.
 */
export function playHullHit(ctx, dest) {
  const now = ctx.currentTime;

  const osc = ctx.createOscillator();
  osc.type = "sine";
  osc.frequency.setValueAtTime(60, now);
  osc.frequency.exponentialRampToValueAtTime(30, now + 0.2);

  const env = ctx.createGain();
  env.gain.setValueAtTime(0, now);
  env.gain.linearRampToValueAtTime(0.3, now + 0.005);
  env.gain.exponentialRampToValueAtTime(0.001, now + 0.25);

  osc.connect(env).connect(dest);
  osc.start(now);
  osc.stop(now + 0.3);

  // Add a noise layer for impact texture
  const noiseBuf = createNoiseBuffer(ctx, 0.1);
  const noiseSrc = ctx.createBufferSource();
  noiseSrc.buffer = noiseBuf;

  const lp = ctx.createBiquadFilter();
  lp.type = "lowpass";
  lp.frequency.value = 300;

  const noiseEnv = ctx.createGain();
  noiseEnv.gain.setValueAtTime(0.15, now);
  noiseEnv.gain.exponentialRampToValueAtTime(0.001, now + 0.08);

  noiseSrc.connect(lp).connect(noiseEnv).connect(dest);
  noiseSrc.start(now);
  noiseSrc.stop(now + 0.1);
}

/**
 * Torpedo/missile detonation — layered explosion with sine sweep.
 */
export function playDetonation(ctx, dest) {
  const now = ctx.currentTime;
  const duration = 1.2;

  // Noise burst through lowpass for explosion body
  const noiseBuf = createNoiseBuffer(ctx, duration);
  const noiseSrc = ctx.createBufferSource();
  noiseSrc.buffer = noiseBuf;

  const lp = ctx.createBiquadFilter();
  lp.type = "lowpass";
  lp.frequency.setValueAtTime(800, now);
  lp.frequency.exponentialRampToValueAtTime(100, now + 0.8);

  const noiseEnv = ctx.createGain();
  noiseEnv.gain.setValueAtTime(0, now);
  noiseEnv.gain.linearRampToValueAtTime(0.25, now + 0.01);
  noiseEnv.gain.exponentialRampToValueAtTime(0.001, now + duration);

  noiseSrc.connect(lp).connect(noiseEnv).connect(dest);
  noiseSrc.start(now);
  noiseSrc.stop(now + duration);

  // Sine sweep 200Hz -> 50Hz for bass punch
  const sweep = ctx.createOscillator();
  sweep.type = "sine";
  sweep.frequency.setValueAtTime(200, now);
  sweep.frequency.exponentialRampToValueAtTime(50, now + 0.5);

  const sweepEnv = ctx.createGain();
  sweepEnv.gain.setValueAtTime(0.2, now);
  sweepEnv.gain.exponentialRampToValueAtTime(0.001, now + 0.6);

  sweep.connect(sweepEnv).connect(dest);
  sweep.start(now);
  sweep.stop(now + 0.7);
}

// ============================================================
// ALERT SOUNDS
// ============================================================

/**
 * Lock acquired — ascending two-tone beep (800Hz then 1200Hz).
 */
export function playLockAcquired(ctx, dest) {
  const now = ctx.currentTime;

  for (let i = 0; i < 2; i++) {
    const t = now + i * 0.09;
    const freq = i === 0 ? 800 : 1200;

    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.value = freq;

    const env = ctx.createGain();
    env.gain.setValueAtTime(0, t);
    env.gain.linearRampToValueAtTime(0.15, t + 0.005);
    env.gain.setValueAtTime(0.15, t + 0.07);
    env.gain.linearRampToValueAtTime(0, t + 0.08);

    osc.connect(env).connect(dest);
    osc.start(t);
    osc.stop(t + 0.09);
  }
}

/**
 * Lock lost — descending two-tone beep (1200Hz then 600Hz).
 */
export function playLockLost(ctx, dest) {
  const now = ctx.currentTime;

  for (let i = 0; i < 2; i++) {
    const t = now + i * 0.09;
    const freq = i === 0 ? 1200 : 600;

    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.value = freq;

    const env = ctx.createGain();
    env.gain.setValueAtTime(0, t);
    env.gain.linearRampToValueAtTime(0.12, t + 0.005);
    env.gain.setValueAtTime(0.12, t + 0.07);
    env.gain.linearRampToValueAtTime(0, t + 0.08);

    osc.connect(env).connect(dest);
    osc.start(t);
    osc.stop(t + 0.09);
  }
}

/**
 * Missile warning beep — single high-pitched pulse (call repeatedly).
 */
export function playMissileWarningBeep(ctx, dest) {
  const now = ctx.currentTime;

  const osc = ctx.createOscillator();
  osc.type = "square";
  osc.frequency.value = 2000;

  const env = ctx.createGain();
  env.gain.setValueAtTime(0, now);
  env.gain.linearRampToValueAtTime(0.1, now + 0.005);
  env.gain.setValueAtTime(0.1, now + 0.045);
  env.gain.linearRampToValueAtTime(0, now + 0.05);

  osc.connect(env).connect(dest);
  osc.start(now);
  osc.stop(now + 0.06);
}

// ============================================================
// AMBIENT / CONTINUOUS
// ============================================================

/**
 * Create reactor hum nodes. Returns { start(), stop(), setVolume(v) }.
 * Caller manages lifecycle.
 */
export function createReactorHum(ctx, dest) {
  const osc1 = ctx.createOscillator();
  osc1.type = "sine";
  osc1.frequency.value = 50;

  const osc2 = ctx.createOscillator();
  osc2.type = "sine";
  osc2.frequency.value = 100;

  const gain1 = ctx.createGain();
  gain1.gain.value = 0.05;
  const gain2 = ctx.createGain();
  gain2.gain.value = 0.02;

  const masterGain = ctx.createGain();
  masterGain.gain.value = 0;

  osc1.connect(gain1).connect(masterGain);
  osc2.connect(gain2).connect(masterGain);
  masterGain.connect(dest);

  let started = false;

  return {
    start() {
      if (started) return;
      started = true;
      osc1.start();
      osc2.start();
    },
    stop() {
      if (!started) return;
      try { osc1.stop(); } catch (_) { /* already stopped */ }
      try { osc2.stop(); } catch (_) { /* already stopped */ }
    },
    /** Set volume 0-1 (scales the quiet base gain) */
    setVolume(v) {
      masterGain.gain.setTargetAtTime(
        Math.max(0, Math.min(1, v)),
        ctx.currentTime,
        0.1 // smooth transition
      );
    }
  };
}

/**
 * Create drive burn noise. Returns { start(), stop(), setThrottle(t) }.
 * Gain proportional to throttle (0-1), bandpass at 150Hz.
 */
export function createDriveBurn(ctx, dest) {
  // Use a long noise buffer looped
  const buf = createNoiseBuffer(ctx, 2);
  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.loop = true;

  const bp = ctx.createBiquadFilter();
  bp.type = "bandpass";
  bp.frequency.value = 150;
  bp.Q.value = 0.8;

  const masterGain = ctx.createGain();
  masterGain.gain.value = 0;

  src.connect(bp).connect(masterGain);
  masterGain.connect(dest);

  let started = false;

  return {
    start() {
      if (started) return;
      started = true;
      src.start();
    },
    stop() {
      if (!started) return;
      try { src.stop(); } catch (_) { /* already stopped */ }
    },
    /** Set throttle 0-1 — controls volume */
    setThrottle(t) {
      const vol = Math.max(0, Math.min(1, t)) * 0.12; // max 0.12 gain
      masterGain.gain.setTargetAtTime(vol, ctx.currentTime, 0.05);
    }
  };
}
