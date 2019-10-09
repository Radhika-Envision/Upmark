'use strict'

angular.module('vpac.utils.math', [])


.factory('Numbers', [function() {
    var Numbers = {
        /**
         * Find the modulo of two numbers, using floored division.
         * http://stackoverflow.com/a/3417242/320036
         * http://en.wikipedia.org/wiki/Modulo_operation
         */
        mod: function(dividend, divisor) {
            return ((dividend % divisor) + divisor) % divisor;
        },
        /**
         * Linear interpolation between two values, e.g. lerp(1, 3, 0.5) == 2
         */
        lerp: function(a, b, fraction) {
            return ((b - a) * fraction) + a;
        },
        /**
         * Inverse linear interpolation between two values. Formally:
         *
         *    lerp(a, b, unlerp(a, b, x)) == x
         *
         * e.g. unlerp(1, 3, 2) == 0.5
         *
         * If a == b, the result is always 0.
         */
        unlerp: function(a, b, value) {
            var divisor = b - a;
            if (divisor == 0)
                return 0;
            return (value - a) / divisor;
        },
        /**
         * Stable function to transform an integer into a seemingly random
         * real number between 0.0 and 1.0.
         */
        hash: function(x) {
            // Robert Jenkins' 32 bit integer hash function.
            // http://stackoverflow.com/a/3428186/320036
            // The prime given on the first line happens to give a good result
            // for boolean datasets.
            var seed = x ^ 1376312589;
            seed = ((seed + 0x7ed55d16) + (seed << 12))  & 0xffffffff;
            seed = ((seed ^ 0xc761c23c) ^ (seed >>> 19)) & 0xffffffff;
            seed = ((seed + 0x165667b1) + (seed << 5))   & 0xffffffff;
            seed = ((seed + 0xd3a2646c) ^ (seed << 9))   & 0xffffffff;
            seed = ((seed + 0xfd7046c5) + (seed << 3))   & 0xffffffff;
            seed = ((seed ^ 0xb55a4f09) ^ (seed >>> 16)) & 0xffffffff;
            return (seed & 0xfffffff) / 0x10000000;
        },
        /**
         * Convert an integer to a character ID - e.g. 0 -> a, 1 -> b, 25 -> z,
         * 26 -> aa, 27 -> ab, etc.
         */
        idOf: function(i) {
            return (i >= 26 ? Numbers.idOf((i / 26 >> 0) - 1) : '') +
                'abcdefghijklmnopqrstuvwxyz'[i % 26 >> 0];
        }
    };
    return Numbers;
}])


;
