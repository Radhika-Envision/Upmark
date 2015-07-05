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
