'use strict'

angular.module('vpac.utils.events', [])


/**
 * Focus an element in response to an event.
 */
.directive('focusOn', [function() {
    return {
        restrict: 'A',
        link: function(scope, element, attrs) {
            var remove = null;
            scope.$watch(attrs.focusOn, function(focusOn) {
                if (remove)
                    remove();
                remove = scope.$on(focusOn, function(event) {
                    console.log('focusOn', event)
                    element.focus();
                });
            });
            scope.$on('$destroy', function() {
                element = null;
                remove = null;
            });
        }
    }
}])


/**
 * Return focus to the last-focussed element in response to an event.
 */
.directive('blurOn', ['$window', '$document', function($window, $document) {
    return {
        restrict: 'A',
        link: function(scope, element, attrs) {
            var lastFocussedElement = null;

            var globalFocusHandler = function(event) {
                var target = angular.element(event.target);
                if (target.prop('tagName') === undefined) {
                    // Don't store window; it may be only temporarily focussed
                    // when the user switches back to the window.
                } else if (!element.is(target)) {
                    lastFocussedElement = target;
                }
            };
            angular.element($window).on('focusin', globalFocusHandler);

            var remove = null;
            scope.$watch(attrs.blurOn, function(blurOn) {
                if (remove)
                    remove();
                remove = scope.$on(blurOn, function(event) {
                    console.log('blurOn', event)
                    if (!element.is(':focus'))
                        return;

                    var lastElem = lastFocussedElement;
                    lastFocussedElement = null;

                    // Transfer focus to last selected element, or fall back to
                    // window if lastElem can't be focussed.
                    if (lastElem && $.contains($document[0].documentElement,
                                               lastElem[0]))
                        lastElem.focus();
                    else
                        element.blur();
                });
            });

            scope.$on('$destroy', function() {
                lastFocussedElement = null;
                scope = null;
                element = null;
                attrs = null;
                remove = null;
                angular.element($window).off('focusin', globalFocusHandler);
            });
        }
    }
}])
