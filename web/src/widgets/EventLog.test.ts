import { describe, expect, it } from 'vitest';
import { eventLogText, eventsForLog, firstSentence } from './EventLog.helpers';

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

  it('keeps only the first sentence of model-limit halt events', () => {
    const longText =
      'Halted: the SG collapsed liquid fraction reached the lower model-validity boundary. ' +
      'The simulator holds the last valid state. Reset Simulation to continue.';

    expect(eventLogText(longText)).toBe(
      'Halted: the SG collapsed liquid fraction reached the lower model-validity boundary.',
    );
  });

  it('collapses newlines before taking a halt summary sentence', () => {
    expect(firstSentence('first line\ncontinues here. second sentence.')).toBe('first line continues here.');
  });

  it('leaves routine command events exactly as events.ts produced them', () => {
    expect(eventLogText('Speed set to 10×')).toBe('Speed set to 10×');
  });
});
