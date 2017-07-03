'use strict'

angular.module('vpac.widgets.size', [])


.directive('autoresize', [function() {
    return {
        restrict: 'AC',
        require: '?ngModel',
        link: function(scope, elem, attrs, ngModel) {
            var resize = function() {
                // Resize to something small first in case we should shrink -
                // otherwise scrollHeight will be wrong.
                elem.css('height', '10px');
                var height = elem[0].scrollHeight;
                height += elem.outerHeight() - elem.innerHeight();
                elem.css('height', '' + height + 'px');
            };

            //elem.on('input change propertychange', resize);
            scope.$watch(function() {return ngModel.$viewValue; }, resize);

            scope.$on('$destroy', function() {
                elem.off();
                elem = null;
            });
        }
    };
}])


/**
 * Takes its height from a child element. This allows CSS transitions to be used
 * for the natural height of the element.
 */
.directive('surrogateHeight', [function() {
    return {
        restrict: 'AC',
        controller: [function() {}],
        require: 'surrogateHeight',
        link: function(scope, elem, attrs, surrogateHeight) {
            surrogateHeight.update = function(height) {
                elem.height(height);
            };
            if (attrs.surrogateHeight != '')
                elem.height(Number(attrs.surrogateHeight));
        }
    };
}])


.directive('surrogateHeightTarget', [function() {
    return {
        restrict: 'AC',
        require: '^surrogateHeight',
        link: function(scope, elem, attrs, surrogateHeight) {
            scope.$watch(function() {
                return elem[0].scrollHeight;
            }, function(height) {
                surrogateHeight.update(height);
            });
        }
    };
}])
