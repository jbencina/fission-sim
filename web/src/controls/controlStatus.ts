/**
 * Compatibility exports for status derivation used by control widgets.
 *
 * The shared implementation lives in `state/plantStatus.ts` so controls,
 * readouts and events classify selected-vs-effective plant state the same
 * way from a single telemetry frame.
 *
 * @module controlStatus
 */

export {
  PENDING_DETAIL,
  clampFraction,
  deriveDumpStatus,
  deriveFeedwaterModeStatus,
  deriveLevelStatus,
  deriveRodModeStatus,
  deriveTurbineTripStatus,
  feedwaterDemandFraction,
  feedwaterSaturation,
  turbineTripCause,
} from '../state/plantStatus'

export type {
  DumpStatus,
  FeedwaterModeStatus,
  FeedwaterSaturation,
  LevelStatus,
  PlantBand,
  RodModeStatus,
  StatusTone,
  TurbineTripCause,
  TurbineTripStatus,
} from '../state/plantStatus'
