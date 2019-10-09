'use strict'

angular.module('vpac.widgets.progress', [])


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
        templateUrl: 'images/clock.svg',
        templateNamespace: 'svg',
        replace: true,
        scope: {
            fraction: '='
        },
        link: function(scope, elem, attrs) {
            var update = function(fraction) {
                var path = drawSemicircle(fraction);
                var fillElem = elem.find(".clock-fill");
                fillElem.attr('d', path);
            };
            update(scope.fraction);
            scope.$watch('fraction', update);
            scope.$on('$destroy', function() {
                scope = null;
                elem = null;
                attrs = null;
            });
        }
    };
}])


.directive('columnProgress', [function() {
    return {
        restrict: 'E',
        scope: {
            items: '='
        },
        templateUrl: "bar-progress.html",
        controller: ['$scope', function($scope) {
            $scope.$watch('items', function(items) {
                if (!items) {
                    $scope.summary = '';
                    return;
                }
                var summary = [];
                for (var i = 0; i < items.length; i++) {
                    var item = items[i];
                    summary.push(item.name + ': ' + item.value);
                }
                $scope.summary = summary.join(', ');
            });
        }],
        link: function(scope, elem, attrs) {
            elem.on('click', function(event) {
                event.preventDefault();
                event.stopPropagation();
            });
            scope.$on('$destroy', function() {
                elem.off('click');
            });
        }
    };
}])


.directive('columnProgressColumn', [function() {
    return {
        restrict: 'A',
        link: function(scope, elem, attrs) {
            scope.$watch('item.fraction', function(fraction) {
                elem.css('height', '' + (fraction * 100) + '%');
                elem.toggleClass('complete', fraction > 0.999999);
            });
        }
    };
}])


;
