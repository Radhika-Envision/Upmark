'use strict';

angular.module('vpac.widgets', [])

/**
 * Draws a progress bar as a clock face (pie chart).
 */
.directive('clockProgress', [function() {
    var drawSemicircle = function(fraction) {
        var path = "M 0,-1";
        if (fraction <= 0)
            return path;

        // The arc might not look good if drawn more than 90 degrees at a time.
        path += " A";
        if (fraction > 0.26)
            path += " 1,1 0 0 1 1,0";
        if (fraction > 0.51)
            path += " 1,1 0 0 1 0,1";
        if (fraction > 0.76)
            path += " 1,1 0 0 1 -1,0";

        var angle = (Math.PI * 2) * fraction;
        var x = Math.sin(angle);
        var y = -Math.cos(angle);
        path += " 1,1 0 0 1 " + x + "," + y;

        if (fraction >= 1.0) {
            path += " 1,1 0 0 1 0,1";
        } else {
            path += " L";
            path += "0,0";
        }

        path += " z";

        return path;
    };

    return {
        restrict: 'E',
        template: '<object data="images/clock.svg" class="clock-progress" type="image/svg+xml"></object>',
        replace: true,
        scope: {
            fraction: '='
        },
        link: function(scope, elem, attrs) {
            var init = function() {
                scope.$watch('fraction', function(fraction) {
                    var svg = elem[0].getSVGDocument();
                    var path = drawSemicircle(fraction);
                    var fillElem = $(svg).find("#clock-fill");
                    fillElem.attr('d', path);
                });
            };
            elem.one('load', init);
        }
    };
}])
;
