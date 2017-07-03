'use strict'

angular.module('vpac.widgets.docs', [])


.service('docsService', [function() {
    this.add = null;
}])


.directive('docs', ['docsService', function(docsService) {
    return {
        restrict: 'E',
        template: '<li ng-transclude></li>',
        replace: true,
        transclude: true,
        link: function(scope, elem, attrs) {
            docsService.add(elem);
            scope.$on('$destroy', function() {
                docsService.remove(elem);
            });
        }
    };
}])


.directive('docsRenderer', ['docsService', 'scopeUtils',
        function(docsService, scopeUtils) {
    return {
        restrict: 'EA',
        scope: {},
        templateUrl: 'docs.html',
        link: function(scope, elem, attrs) {
            scope.ndocs = 0;
            scope.isCollapsed = true;
            docsService.add = function(transcludeElem) {
                var container = elem.children().children('ul.docs');
                var path = scopeUtils.path(transcludeElem.scope());
                var child = container.children().first();
                while (child.length) {
                    var childPath = scopeUtils.path(child.scope());
                    if (childPath > path)
                        break;
                    child = child.next();
                }
                if (child.length)
                    child.before(transcludeElem);
                else
                    container.append(transcludeElem);
                scope.ndocs++;
            };
            docsService.remove = function(transcludeElem) {
                transcludeElem.remove();
                scope.ndocs--;
            };
            scope.$on('$destroy', function() {
                docsService.add = null;
            });
        }
    };
}])


.service('scopeUtils', [function() {
    /**
     * Finds the path to a scope, e.g. the second child of the root scope would
     * have a path of 00000.00001.
     */
    this.path = function(scope) {
        var path;
        var ord;
        if (scope.$parent) {
            path = this.path(scope.$parent);
            ord = 0;
            var sibling = scope.$parent.$$childHead;
            while (sibling != scope) {
                ord++;
                sibling = sibling.$$nextSibling;
            }
        } else {
            path = '';
            ord = 0;
        }
        // Pad ordinal with zeros
        ord = ('00000' + ord).slice(-5);
        return path + ord + '.';
    };
}])
