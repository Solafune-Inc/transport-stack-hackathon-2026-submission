import { groupStops, routeParts, searchStops } from '../logic/lookup';
import type { NetStop } from '../types';

it('splits route ids into number and direction like the server', () => {
  expect(routeParts('623UP')).toEqual(['623', 'UP']);
  expect(routeParts('116ADOWN2')).toEqual(['116A', 'DOWN']);
  expect(routeParts('DS CIRCULAR')).toEqual(['DS CIRCULAR', null]);
});

describe('stop search', () => {
  const stop = (id: string, name: string, lat: number, nRoutes = 1): NetStop => ({ id, name, lat, lon: 77, nRoutes });
  const groups = groupStops([
    stop('a', 'Shahdara Terminal', 28.67, 5),
    stop('b', 'Shahdara  terminal ', 28.6702, 9),
    stop('c', 'Shahdara Terminal', 28.8),
    stop('d', 'New Shahdara', 28.6),
  ]);

  it('merges same-named stops across the road but keeps far-apart ones separate', () => {
    expect(groups.map((g) => [g.id, g.ids, g.nRoutes])).toEqual([
      ['d', ['d'], 1],
      ['b', ['b', 'a'], 9],
      ['c', ['c'], 1],
    ]);
  });

  it('lists names starting with the query before names containing it', () => {
    expect(searchStops(groups, 'shah').map((g) => g.id)).toEqual(['b', 'c', 'd']);
    expect(searchStops(groups, '  ')).toEqual([]);
  });
});
