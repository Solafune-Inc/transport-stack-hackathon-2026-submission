import { pointAtDistance } from '../logic/shape';

describe('pointAtDistance', () => {
  it('interpolates along the shape and clamps at both ends', () => {
    const shape: [number, number, number][] = [[28, 77, 0], [28, 77.1, 1000], [28.1, 77.1, 2000]];
    expect(pointAtDistance(shape, 500)).toEqual([28, 77.05]);
    expect(pointAtDistance(shape, -5)).toEqual([28, 77]);
    expect(pointAtDistance(shape, 5000)).toEqual([28.1, 77.1]);
  });
});
