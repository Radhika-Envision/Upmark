#!/bin/bash

imgdir=$(dirname $0)

# High-res icons show full image
for size in 72 96 128 144 192; do
    inkscape -z -w $size -h $size --export-area-page \
        --export-png=${imgdir}/logo-monogram-$size.png ${imgdir}/logo-monogram.svg
done

# Low-res icons show clipped image
for size in 32 36 48 64; do
    inkscape -z -w $size -h $size --export-area=25:60:155:190 \
        --export-png=${imgdir}/logo-monogram-$size.png ${imgdir}/logo-monogram.svg
done

# Optimised SVG files
function optimise_svg() {
    SCOUR_OPTS="\
        --disable-group-collapsing \
        --indent=none \
        --remove-metadata \
        --enable-id-stripping \
        --protect-ids-noninkscape \
        --enable-comment-stripping \
        --set-precision=5"
    python -m scour $SCOUR_OPTS -i "$1" \
        | sed -r 's/(id="|\(#|href="#)([^)"0-9]+)([0-9]+["\)])/\1'"$3"'\2\3/g' \
        > "$2"
}
optimise_svg "${imgdir}/logo.svg" "${imgdir}/logo.min.svg" 'logo-'
optimise_svg "${imgdir}/logo-monogram.svg" "${imgdir}/logo-monogram.min.svg" 'monogram-'
optimise_svg "${imgdir}/clock.svg" "${imgdir}/clock.min.svg" 'clock-'
