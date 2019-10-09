'use strict'

angular.module('vpac.widgets.dimmer', [])


.service('dimmer', function() {
    this.dimmers = [];
    this.add = function(key) {
        var i = this.dimmers.indexOf(key);
        if (i >= 0)
            return;
        this.dimmers = this.dimmers.concat(key);
    };
    this.remove = function(key) {
        var i = this.dimmers.indexOf(key);
        if (i < 0)
            return;
        var dimmers = this.dimmers.slice();
        dimmers.splice(i, 1);
        this.dimmers = dimmers;
    };
    this.dismiss = function() {
        this.dimmers.forEach(function(dimmer) {
            dimmer.dismiss();
        });
    };
})


.directive('highlight', function(dimmer, $parse) {
    return {
        restrict: 'A',
        link: function(scope, elem, attrs) {
            var dismiss = attrs.highlightDismiss ?
                $parse(attrs.highlightDismiss) : null;
            var key = {
                dismiss: function() {
                    if (dismiss)
                        dismiss(scope);
                }
            };
            if (attrs.highlight) {
                scope.$watch(attrs.highlight, function(highlight) {
                    if (highlight)
                        dimmer.add(key);
                    else
                        dimmer.remove(key);
                    elem.toggleClass('undim', !!highlight);
                });
            } else {
                // Highlight directive given with no qualification = always
                // highlight
                dimmer.add(key);
                elem.toggleClass('undim', true);
            }
            scope.$on('$destroy', function(event) {
                dimmer.remove(key);
                key = dismiss = scope = null;
            });
        }
    };
})


.directive('highlightAny', function(dimmer, $parse) {
    return {
        restrict: 'A',
        link: function(scope, elem, attrs) {
            scope.dimmer = dimmer;
            scope.$watch('dimmer.dimmers.length > 0', function(highlight) {
                elem.toggleClass('undim', !!highlight);
            });
        }
    };
})


.directive('dimmer', ['dimmer', function(dimmer) {
    return {
        restrict: 'C',
        link: function(scope, elem, attrs) {
            scope.dimmer = dimmer;
            scope.$watch('dimmer.dimmers.length > 0', function onDim(dim) {
                scope.dim = dim;
            });
        }
    };
}])
