'use strict'

angular.module('vpac.widgets.visibility', [])


.directive('ngUncloak', ['$timeout', function($timeout) {
    return {
        restrict: 'A',
        link: function(scope, elem, attrs) {
            elem.toggleClass('ng-uncloak', true);
            elem.toggleClass('in', false);
            $timeout(function() {
                elem.toggleClass('ng-hide', true);
            }, 2000);
        }
    };
}])


.directive('ifNotEmpty', function() {
    return {
        restrict: 'AC',
        link: function(scope, elem, attrs) {
            scope.$watch(
                function isEmpty() {
                    var content = elem.html();
                    // [\s\S] matches new lines:
                    // http://stackoverflow.com/a/1068308/320036
                    content = content.replace(/<!--[\s\S]*?-->/g, '');
                    content = content.trim();
                    return content == '';
                },
                function toggle(empty) {
                    elem.toggleClass('ng-hide', empty);
                });
        }
    };
})
