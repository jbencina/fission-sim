import { describe, expect, it } from 'vitest';
import { EVENT_SUMMARY_MAX_CHARS, eventLogText, eventsForLog, haltSummary, truncateWithEllipsis } from './EventLog.helpers';

const ACTUAL_SG_TUBE_UNCOVERING_MESSAGE =
  "Steam-generator collapsed liquid fraction fell below the conservative 30 % surrogate model limit for the top of the tube bundle: with tubes uncovered the model's constant heat-transfer coefficient no longer applies. This is a simulation validity limit, not a plant elevation or protection setpoint; in a real plant a low-low level trip and auxiliary feedwater would have acted long before this. The simulation stopped at t = 66.0 s, the last valid state, and shows that state. Reset the simulation to start again. Reset keeps your pressure setpoint, speed, turbine admission demand, rod-control mode, SG level setpoint, and pause state; it clears SCRAM, the turbine trip latch, and manual feedwater, and the rod command returns to 50 %. Change the setting that caused this, or the same thing will happen again.";

describe('EventLog rendering helpers', () => {
  it('orders retained events newest first without dropping older retained rows', () => {
    const events = Array.from({ length: 8 }, (_, i) => ({
      t: i,
      text: `Event ${i}`,
      level: 'info' as const,
    }));

    const shown = eventsForLog(events);

    expect(shown).toHaveLength(8);
    expect(shown.map((event) => event.text)).toEqual([
      'Event 7',
      'Event 6',
      'Event 5',
      'Event 4',
      'Event 3',
      'Event 2',
      'Event 1',
      'Event 0',
    ]);
  });

  it('summarizes the actual SG tube-uncovering backend halt message on one bounded line', () => {
    const text = eventLogText(`Halted: ${ACTUAL_SG_TUBE_UNCOVERING_MESSAGE}`);

    expect(text).toBe('Halted: SG tubes uncovered — see the notice above');
    expect(text.length).toBeLessThanOrEqual(EVENT_SUMMARY_MAX_CHARS);
  });

  it('uses a generic model-limit halt summary for unknown messages', () => {
    expect(haltSummary('An unfamiliar long model-limit explanation. More detail follows.')).toBe(
      'Halted at a model limit — see the notice above',
    );
  });

  it('truncates overlong one-line summaries with an ellipsis', () => {
    expect(truncateWithEllipsis('first line\ncontinues with too many words', 18)).toBe('first line contin…');
  });

  it('leaves routine command events exactly as events.ts produced them', () => {
    expect(eventLogText('Speed set to 10×')).toBe('Speed set to 10×');
  });

  it('keeps the original event text for an optional tooltip/title', () => {
    const shown = eventsForLog([{ t: 1, text: `Halted: ${ACTUAL_SG_TUBE_UNCOVERING_MESSAGE}`, level: 'alarm' }]);

    expect(shown[0].text).toBe('Halted: SG tubes uncovered — see the notice above');
    expect(shown[0].fullText).toBe(`Halted: ${ACTUAL_SG_TUBE_UNCOVERING_MESSAGE}`);
  });
});
