"""
Helper to get good pdf exports from draw.io in the prescence of custom fonts.

Problems with simpler alternatives:
1. (Easiest, definitely try it first!) Export as SVG from chrome: chrome messess up the font weight in my case, making the bold parts too "bold". Probably an artifact of the specific font I'm using.
2. Export As PDF from firefox/chrome: Breaks custom fonts.
3. "Print" from the draw.io menu in firefox: Rasterizes some shape outlines. Doesn't respect custom page size.
4. "Save As HTML" from the print preview in firefox (during step 2 of workflow below): Saves some default draw.io page instead of the actual diagram.
5. Inkscape to convert svg to pdf- doesn't embed fonts.
6. Imagemagick to convert svg to pdf- rasterizes everything.

My workflow:
1. Export the current page as SVG from firefox with "Embed Fonts" option
    - I usually use "size: Diagram" option
2. Dump the <html> from the Print Preview of draw.io (on firefox) using `document.documentElement.outerHTML` in the browser console.
    - I usually use "Crop" option to fit page to diagram.
    - Have written a Tampermonkey script for this. See [js_usercripts/drawio_dump.js]
3. Run this script. It will do two things-
    1. Extract the `@page gePageFormat` CSS rule from the html. This specifies the page size, so chrome's PDF knows the diagram size.
    2. Insert some CSS fixes for chrome messing up the mathjax symbols (from https://github.com/marp-team/marp-core/issues/287)
4. Open the output html in chrome and Print -> Save As PDF.

Known bugs:
1. Sometimes, the page margins don't match between firefox and chrome, leading to some parts of the diagram being cut off (very thin, happens near borders).
    - This usually manifests as multiple pages in Chrome's print preview.
    - The current fix is to manually edit the html output of this file to increase some of the page margins (+0.1 inches typically works.)
    - TODO: This script itself should parse the css rule and allow applying an offset.
"""

import argparse
import re

from pathlib import Path

parser = argparse.ArgumentParser()
# TODO: We technically only need the style with page dims, not the entire HTML
parser.add_argument("html", type=Path, help="Dumped HTML")
parser.add_argument("svg", nargs="?", type=Path, help="Exported SVG")
parser.add_argument("--output-path", default=None, type=Path, help="Path to output html. Uses path derived from svg file (name.svg->name.html) by default. WARNING: If svg arg is not specified, this will overwrite the input html.")
args = parser.parse_args()

if not args.svg:
    args.svg = args.html.with_suffix(".svg")
if not args.output_path:
    args.output_path = args.svg.with_suffix(".html")

# classic: https://stackoverflow.com/questions/1732348/
m = re.search(r"@page geP[^/]*", args.html.read_text(), re.MULTILINE)
assert m
page_style = """<style type="text/css">{}/style>""".format(m.group(0))

preamble = """
<html>
<head>
    {}
</head>
<body>
<div id="container" class="gePageFormat-___-___">
""".format(page_style)

post = """</div>
<style>
@media print {
  mjx-container[jax="SVG"] :is(use[data-c], path[data-c]) {
    stroke-width: 0;
  }
}
</style>

</body>
</html>"""

svg_node = [line for line in args.svg.read_bytes().splitlines() if line.startswith(b"<svg")][0]
wrapped = preamble.encode() + svg_node + post.encode()

args.output_path.write_bytes(wrapped)
