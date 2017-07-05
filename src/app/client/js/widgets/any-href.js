'use strict'

angular.module('vpac.widgets.any-href', [])


.directive('anyHref', ['$location', function($location) {
    return {
        restrict: 'A',
        link: function(scope, elem, attrs) {
            elem.on('click.anyHref', function() {
                if (attrs.disabled)
                    return;
                scope.$apply(function() {
                    $location.url(attrs.anyHref);
                });
            });
            scope.$on('$destroy', function() {
                elem.off('.anyHref');
                scope = null;
            });
        }
    };
}])


;
