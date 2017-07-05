'use strict'

angular.module('vpac.utils.string', [])


/*
 * Simple string interpolation. E.g.
 *
 * format('foo {} {} {}', 'a', 'b', 'c');
 * "foo a b c"
 *
 * format('foo {2} {1} {0}', 'a', 'b', 'c');
 * "foo c b a"
 *
 * format('foo {2} {1} {0}', ['a', 'b', 'c']);
 * "foo c b a"
 *
 * format('foo {bar} {baz}', {bar: "a", baz: "b"});
 * "foo a b"
 */
.factory('format', ['$filter', function($filter) {
    var re = /(^|[^\\]){([^{}]*)}/g;
    var json = $filter('json');

    return function write(format, args) {
        var autoIndex = 0;
        var offset = 0;
        if (!angular.isObject(args) && !angular.isArray(args)) {
            args = arguments;
            offset = 1;
        }
        var message = format.replace(re, function(match, prefix, key) {
            if (key == "")
                key = autoIndex++;
            var ordinal = Number(key);
            if (!isNaN(ordinal))
                key = ordinal + offset;
            var value = args[key];
            if (value === undefined)
                return match;
            else if (angular.isObject(value))
                return json(value);
            else
                return prefix + value;
        });
        return message;
    };
}])


.factory('Strings', [function() {
    return {
        /**
         * Generate an integer hash code from a string.
         */
        hashCode: function(str) {
            // http://www.cse.yorku.ca/~oz/hash.html
            // http://stackoverflow.com/a/7616484/320036
            var hash = 0;
            for (i = 0; i < this.length; ++i) {
                var chr = str.charCodeAt(i);
                hash = ((hash << 5) - hash) + chr;
                hash = hash & hash;
            }
            return hash;
        }
    };
}])


;
