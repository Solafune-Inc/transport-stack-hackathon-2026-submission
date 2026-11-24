import { LEVEL_LABEL, LEVEL_ORDER, OVER_CAPACITY_OCC, describeLoad } from '../logic/crowding';

describe('describeLoad', () => {
  it('rounds the passenger count to 5', () => {
    expect(describeLoad(0.02, 60)).toBe('Almost empty');
    expect(describeLoad(0.5, 60)).toBe('~30 on board · capacity 60');
    expect(describeLoad(1.2, 60)).toBe('~70 on board · capacity 60');
  });

  it('says "Over capacity" instead of an implausible count', () => {
    expect(describeLoad(OVER_CAPACITY_OCC, 60)).toBe('~90 on board · capacity 60');
    expect(describeLoad(1.51, 60)).toBe('Over capacity (capacity 60)');
    expect(describeLoad(7.6, 60)).toBe('Over capacity (capacity 60)');
  });
});

it('gives every level a rider-facing label', () => {
  expect(LEVEL_ORDER.map((l) => LEVEL_LABEL[l])).toEqual(['Seats available', 'Standing room', 'Crowded', 'Packed']);
});
