# Bundled font

`Aileron-Regular.otf` is used to render the fictional specimen cards.

- **Font:** Aileron Regular, version 0102, by Sora Sagano (dotcolon).
- **Source:** https://dotcolon.net/font/aileron/ (archive `aileron_0102.zip`,
  SHA-256 `a93a1327f44912a7b1410ad0056fec3e904074413b0bd9da550f6175587cf958`).
- **License:** [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/) (public
  domain dedication), as stated by the publisher. The file is redistributed unmodified.

It is bundled because the subset of Aileron embedded in Pillow (`ImageFont.load_default`) has
no accented glyphs. Without it, names such as "João" or "Gonçalves" were drawn with placeholder
glyphs.
