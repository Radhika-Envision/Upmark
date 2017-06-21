import re

import math_utils


class Color:

    COLOR_PATTERN = re.compile(
        r'#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})?',
        flags=re.IGNORECASE)

    def __init__(self, r, g, b, a=1):
        self.r = r
        self.g = g
        self.b = b
        self.a = a

    @classmethod
    def parse(cls, hex_str):
        match = Color.COLOR_PATTERN.match(hex_str)
        r = int(match.group(1), 16) / 255
        g = int(match.group(2), 16) / 255
        b = int(match.group(3), 16) / 255
        if match.group(4):
            a = int(match.group(4), 16) / 255
        else:
            a = 1
        return cls(r, g, b, a)

    @property
    def brightness(self):
        return (self.r + self.g + self.b) / 3

    @property
    def is_dark(self):
        return self.brightness < 0.6

    @property
    def rgba_str(self):
        if self.a == 1:
            return "rgb({}, {}, {})".format(
                int(self.r * 255), int(self.g * 255), int(self.b * 255))
        else:
            return "rgba({}, {}, {}, {:0.2f})".format(
                int(self.r * 255), int(self.g * 255), int(self.b * 255), self.a)

    def mix(self, other, fraction):
        return Color(
            math_utils.lerp(self.r, other.r, fraction),
            math_utils.lerp(self.g, other.g, fraction),
            math_utils.lerp(self.b, other.b, fraction),
            math_utils.lerp(self.a, other.a, fraction),
        )

    def twotone_complement(self, amount):
        if self.is_dark:
            return self.mix(Color(1, 1, 1), amount)
        else:
            return self.mix(Color(0, 0, 0), amount)

    def __str__(self):
        return self.rgba_str

    def __repr__(self):
        return self.rgba_str
