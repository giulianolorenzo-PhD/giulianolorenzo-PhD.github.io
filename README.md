# giulianolorenzo-PhD.github.io

Personal landing page in the style of an Omarchy terminal running `fastfetch`
(Everforest theme, JetBrainsMono Nerd Font), with an ASCII-art portrait.

Static files only: `index.html`, `assets/`. No build step.

## Preview locally

```sh
python3 -m http.server 8000
# open http://localhost:8000
```

## Art styles

With `SHOW_PICKER = true`, a bottom bar switches between the portrait styles (keys `1`–`7`, `←`/`→`).
`?ascii=<id>` in the URL selects one directly, e.g. `?ascii=mono-half`.

To fix one style and hide the bar, edit the top of `assets/main.js`:

```js
const DEFAULT_ART = "color-chars";
const SHOW_PICKER = false;
```

## Regenerating the portrait

`assets/ascii.js` is generated from `tools/avatar-cutout.png`
(the GitHub avatar with the background removed by `rembg`):

```sh
pip install pillow numpy
python tools/gen_ascii.py                    # writes assets/ascii.js
python tools/gen_ascii.py --preview /tmp/p   # also writes PNG previews
```

For a new photo: remove the background (`pip install "rembg[cpu]"`,
then `rembg i photo.jpg tools/avatar-cutout.png`), adjust `CROP` in
`tools/gen_ascii.py` to frame head and shoulders, and run the script again.

## Credits

JetBrains Mono / Nerd Fonts (SIL Open Font License, `assets/fonts/OFL.txt`),
subset to the glyphs this page uses. Colours: Everforest by sainnhe.
