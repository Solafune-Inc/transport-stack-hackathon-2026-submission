import { CHANGE_PENALTY_MIN, CROWD_PENALTY_MIN, changeText, findLeaveLater, sortOptions, toOptions, type JourneyOption } from '../logic/planner';

const option = (over: Partial<JourneyOption>): JourneyOption => ({
  routeId: 'A',
  trip: 0,
  fromPos: 0,
  toPos: 1,
  fromStop: 'a',
  toStop: 'b',
  depart: 0,
  arrive: 0,
  waitMin: 0,
  rideMin: 0,
  totalMin: 0,
  occ: 0,
  level: 'Low',
  confidence: 'high',
  legs: [],
  changes: 0,
  walkMin: 0,
  score: 0,
  ...over,
});

describe('ranking', () => {
  const crowdedFast = option({ routeId: 'fast', arrive: 1000, level: 'Very High', score: 10 + CROWD_PENALTY_MIN['Very High'] });
  const emptySlow = option({ routeId: 'slow', arrive: 1600, level: 'Low', score: 20 });

  it('orders by arrival, by crowding, or by time plus a crowding penalty', () => {
    expect(sortOptions([emptySlow, crowdedFast], 'fastest')[0].routeId).toBe('fast');
    expect(sortOptions([crowdedFast, emptySlow], 'least_crowded')[0].routeId).toBe('slow');
    expect(sortOptions([crowdedFast, emptySlow], 'balanced')[0].routeId).toBe('slow');
  });

  it('suggests a less crowded bus only when the fastest one is High or worse', () => {
    expect(findLeaveLater([crowdedFast, emptySlow])).toEqual({ option: emptySlow, instead: crowdedFast, extraMin: 10 });
    expect(findLeaveLater([option({ level: 'Medium', arrive: 1000 }), emptySlow])).toBeNull();
    expect(findLeaveLater([crowdedFast, option({ level: 'Low', arrive: 1000 + 46 * 60 })])).toBeNull();
  });
});

it('turns server options into wait, ride and total minutes with the crowding penalty', () => {
  const [o] = toOptions(
    [{ routeId: 'A', trip: 3, fromPos: 2, toPos: 9, fromStop: 'a', toStop: 'b', depart: 1200, arrive: 2400, occ: 0.9, level: 'High', confidence: 'high' }],
    600,
  );
  expect(o).toMatchObject({ waitMin: 10, rideMin: 20, totalMin: 30, score: 30 + CROWD_PENALTY_MIN.High });
});

it('keeps the rides of a trip with a change and adds the change penalty', () => {
  const leg = (routeId: string, depart: number, arrive: number, fromStop: string, toStop: string) => ({
    routeId, trip: 0, fromPos: 0, toPos: 3, fromStop, toStop, fromName: fromStop.toUpperCase(), toName: toStop.toUpperCase(),
    depart, arrive, occ: 0.3, level: 'Low' as const, confidence: 'high' as const,
  });
  const [direct, change] = toOptions(
    [
      { routeId: 'A', trip: 3, fromPos: 2, toPos: 9, fromStop: 'a', toStop: 'b', depart: 1200, arrive: 2400, occ: 0.3, level: 'Low', confidence: 'high' },
      { routeId: 'B', trip: 1, fromPos: 0, toPos: 3, fromStop: 'a', toStop: 'c', depart: 1200, arrive: 2400, occ: 0.3, level: 'Low', confidence: 'high',
        legs: [leg('B', 1200, 1800, 'a', 'x'), leg('C', 1920, 2400, 'y', 'b')], changes: 1, walk_m: 100, walk_s: 120 },
    ],
    600,
  );
  expect(direct).toMatchObject({ changes: 0, walkMin: 0, score: 30 });
  expect(changeText(direct)).toBe('');
  expect(direct.legs).toHaveLength(1);
  expect(change).toMatchObject({ changes: 1, walkMin: 2, score: 30 + CHANGE_PENALTY_MIN });
  expect(changeText(change)).toBe('Change at X → walk ~2 min to Y · wait ~0 min');
  expect(changeText({ ...change, walkMin: 0, legs: [change.legs[0], { ...change.legs[1], fromStop: 'x' }] })).toBe(
    'Change at X · wait ~2 min',
  );
  expect(change.legs.map((l) => l.routeId)).toEqual(['B', 'C']);
  expect(sortOptions([change, direct], 'fastest')[0]).toBe(direct);
  expect(sortOptions([change, direct], 'balanced')[0]).toBe(direct);
});

it('suggests a less crowded trip only with as many changes', () => {
  const crowdedDirect = option({ routeId: 'fast', arrive: 1000, level: 'Very High' });
  const quietChange = option({ routeId: 'change', arrive: 1300, level: 'Low', changes: 1 });
  expect(findLeaveLater([crowdedDirect, quietChange])).toBeNull();
});
