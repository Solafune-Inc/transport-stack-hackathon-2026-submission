import raw from '../assets/data/meta.json';
import type { Meta } from './types';

/** Attribution + crowding model assumptions, exported by src/export_mobile_data.py (repo root). */
export const META = raw as unknown as Meta;
