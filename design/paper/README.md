# Paper texture

`crumple.html` draws the crumpled-paper background used on the landing page
(`scrollcraft/builds/fairpaper-landing/paper.webp`): a seamless 1600 px tile in the page's `--paper` colour.

How it works: creased paper is a mesh of flat facets. The script scatters points on a torus (so the tile wraps),
triangulates them, gives each point a random height and shades every facet by how it faces a light from the top
left. Two meshes are layered (large folds, small crinkles), the creases are bent slightly and softened, and a fine
grain goes on top. The same seed always gives the same tile.

To make a new one:

1. Open `crumple.html` in a browser. Change any setting through the hash, e.g. `crumple.html#seed=12&depth=0.05`.
2. Press **Save PNG**.
3. Encode it: `ffmpeg -i paper.png -c:v libwebp -quality 85 -compression_level 6 paper.webp` (about 22 KB).
4. Replace `scrollcraft/builds/fairpaper-landing/paper.webp`.

Keep `depth` at 0.06 or below: the darkest creases then still give the lightest grey text (`--faint`) at least
4.5:1 contrast.
