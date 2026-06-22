"""Raster side of the extraction module — the bridge between pixels and the geographic world.

A `Tile` is a north-up affine frame: a top-left (NW) corner in WGS84 and a single
degrees-per-pixel resolution, which is all you need to map a pixel (row, col) to a (lon, lat)
and back. Real imagery arrives with exactly this (a GeoTIFF's affine transform); we build one
to cover a road graph's bounding box so the offline path and the real path are interchangeable.

Everything here is pure NumPy — no GDAL, no Pillow, no scikit-image — which keeps the core's
"installs anywhere" promise intact even though we're now doing image work. The PNG encoder at
the bottom is ~20 lines on top of stdlib zlib, just enough to ship a mask to the browser as a
data URL.
"""

from __future__ import annotations

import base64
import struct
import zlib
from dataclasses import dataclass

import numpy as np

from app.graph.build import haversine_m


@dataclass(frozen=True)
class Tile:
    """North-up affine frame. (lon0, lat0) is the NW corner; `res` is degrees per pixel."""
    lon0: float
    lat0: float
    res: float
    height: int
    width: int

    def to_pixel(self, lon, lat):
        col = int((lon - self.lon0) / self.res)
        row = int((self.lat0 - lat) / self.res)
        return row, col

    def to_lonlat(self, row, col):
        # pixel centre
        lon = self.lon0 + (col + 0.5) * self.res
        lat = self.lat0 - (row + 0.5) * self.res
        return lon, lat

    def bounds(self):
        """[[lat_min, lon_min], [lat_max, lon_max]] — Leaflet image-overlay order."""
        lat_min = self.lat0 - self.height * self.res
        lon_max = self.lon0 + self.width * self.res
        return [[lat_min, self.lon0], [self.lat0, lon_max]]


def tile_for_graph(G, target_px=360, pad_frac=0.06):
    """Build a Tile covering G's node bbox, sized so the longer side is ~`target_px` pixels."""
    xs = [d["x"] for _, d in G.nodes(data=True)]
    ys = [d["y"] for _, d in G.nodes(data=True)]
    lon_min, lon_max = min(xs), max(xs)
    lat_min, lat_max = min(ys), max(ys)
    span = max(lon_max - lon_min, lat_max - lat_min)
    pad = span * pad_frac or 1e-4
    res = (span + 2 * pad) / target_px

    lon0, lat0 = lon_min - pad, lat_max + pad
    width = int(np.ceil((lon_max - lon_min + 2 * pad) / res))
    height = int(np.ceil((lat_max - lat_min + 2 * pad) / res))
    return Tile(lon0=lon0, lat0=lat0, res=res, height=height, width=width)


def rasterize_graph(G, tile, width_px=3):
    """Burn a road graph into a binary mask — the image a *perfect* extractor would return."""
    mask = np.zeros((tile.height, tile.width), dtype=bool)
    for u, v in G.edges():
        r0, c0 = tile.to_pixel(G.nodes[u]["x"], G.nodes[u]["y"])
        r1, c1 = tile.to_pixel(G.nodes[v]["x"], G.nodes[v]["y"])
        for r, c in _bresenham(r0, c0, r1, c1):
            if 0 <= r < tile.height and 0 <= c < tile.width:
                mask[r, c] = True
    return dilate(mask, width_px)


def _bresenham(r0, c0, r1, c1):
    """Integer line pixels from (r0,c0) to (r1,c1)."""
    pts = []
    dr = abs(r1 - r0)
    dc = abs(c1 - c0)
    sr = 1 if r0 < r1 else -1
    sc = 1 if c0 < c1 else -1
    err = dr - dc
    r, c = r0, c0
    while True:
        pts.append((r, c))
        if r == r1 and c == c1:
            break
        e2 = 2 * err
        if e2 > -dc:
            err -= dc
            r += sr
        if e2 < dr:
            err += dr
            c += sc
    return pts


def dilate(mask, radius):
    """Binary dilation by a disk of the given radius (road thickness)."""
    if radius <= 0:
        return mask
    out = mask.copy()
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            if dr * dr + dc * dc > radius * radius or (dr == 0 and dc == 0):
                continue
            out |= _shift(mask, dr, dc)
    return out


def erode(mask, radius):
    """Binary erosion — the dual of dilate, used by morphological opening to drop speckle."""
    if radius <= 0:
        return mask
    out = mask.copy()
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            if dr * dr + dc * dc > radius * radius or (dr == 0 and dc == 0):
                continue
            out &= _shift(mask, dr, dc)
    return out


def _shift(a, dr, dc):
    """Shift array by (dr, dc) with zero fill (no wraparound). out[r+dr, c+dc] = a[r, c]."""
    h, w = a.shape
    out = np.zeros_like(a)
    rs0, rs1 = max(0, -dr), h - max(0, dr)
    cs0, cs1 = max(0, -dc), w - max(0, dc)
    rd0, rd1 = max(0, dr), h - max(0, -dr)
    cd0, cd1 = max(0, dc), w - max(0, -dc)
    out[rd0:rd1, cd0:cd1] = a[rs0:rs1, cs0:cs1]
    return out


def png_data_url(mask, road=(255, 214, 90), bg=(12, 17, 19)):
    """Encode a boolean mask as a tinted PNG data URL — roads bright, background dark — so the
    Repair Lab can drop it under the graph as a Leaflet image overlay. Pure stdlib (zlib)."""
    h, w = mask.shape
    rgb = np.empty((h, w, 3), dtype=np.uint8)
    rgb[...] = bg
    rgb[mask] = road

    raw = bytearray()
    for r in range(h):
        raw.append(0)                       # filter byte 0 (None) per scanline
        raw.extend(rgb[r].tobytes())
    comp = zlib.compress(bytes(raw), 9)

    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)   # 8-bit, colour type 2 (RGB)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", comp) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def polyline_length_m(tile, pixels):
    """Ground length of a traced pixel polyline, via haversine on georeferenced vertices."""
    total = 0.0
    for (r0, c0), (r1, c1) in zip(pixels, pixels[1:]):
        lon0, lat0 = tile.to_lonlat(r0, c0)
        lon1, lat1 = tile.to_lonlat(r1, c1)
        total += haversine_m(lat0, lon0, lat1, lon1)
    return total
