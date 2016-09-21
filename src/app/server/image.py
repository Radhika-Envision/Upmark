import cairosvg
from scour import scour

import config


def clean_svg(svg):
    '''
    Clean up an SVG file.
    - Remove script tags and the like
    - Reduce file size
    @return The SVG data as a string
    '''
    opts = scour.parse_args(args=[
        '--disable-group-collapsing',
        '--enable-viewboxing',
        '--enable-id-stripping',
        '--enable-comment-stripping',
        '--indent=none',
        '--protect-ids-noninkscape',
        '--quiet',
        '--remove-metadata',
        '--set-precision=5',
    ])
    output = scour.scourString(svg, opts)
    return output


def get_icon(session, name, size):
    check_display(name)
    data = config.get_setting(session, name)
    data = clean_svg(data).encode('utf-8')
    bitmap = cairosvg.svg2png(data, parent_width=size, parent_height=size)
    return bitmap


def check_display(name):
    schema = config.SCHEMA.get(name)
    if not schema or config.is_private(name, schema) or schema['type'] != 'image':
        raise KeyError("No such image %s" % name)
