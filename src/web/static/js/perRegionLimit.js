/** Per-region limit constants and clamp helper for Job Search Settings and Spend Confirmation. */

export const PER_REGION_LIMIT_MIN = 25;
export const PER_REGION_LIMIT_MAX = 1000;
export const PER_REGION_LIMIT_DEFAULT = 200;
export const PER_REGION_LIMIT_STEP = 25;

export function clampPerRegionLimit(value) {
  let n = parseInt(value, 10);
  if (isNaN(n)) n = PER_REGION_LIMIT_DEFAULT;
  n = Math.round(n / PER_REGION_LIMIT_STEP) * PER_REGION_LIMIT_STEP;
  return Math.max(PER_REGION_LIMIT_MIN, Math.min(PER_REGION_LIMIT_MAX, n));
}
