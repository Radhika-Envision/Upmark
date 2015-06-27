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


.factory('Notifications', ['log', '$timeout', function(log, $timeout) {
    function Notifications() {
        this.messages = [];
    };
    Notifications.prototype.add = function(id, type, body, duration) {
        var newMessage = {
            id: id,
            type: type,
            css: type == 'error' ? 'danger' : type,
            body: body
        };
        for (var i = 0; i < this.messages.length; i++) {
            if (angular.equals(this.messages[i], newMessage))
                return;
        }
        this.messages = [newMessage].concat(this.messages);

        if (duration) {
            $timeout(function(that, message) {
                that.remove(message);
            }, duration, true, this, newMessage);
        }

        return newMessage;
    };
    /**
     * Remove all messages that match the given ID or object.
     */
    Notifications.prototype.remove = function(messageOrId) {
        var filterFn = null;
        if (angular.isString(messageOrId)) {
            filterFn = function(element) {
                return element.id != this;
            };
        } else {
            filterFn = function(element) {
                return element != this;
            };
        }
        return this.messages = this.messages.filter(filterFn, messageOrId);
    };
    return new Notifications();
}])


.directive('messages', [function() {
    return {
        restrict: 'E',
        templateUrl: 'messages.html',
        replace: true,
        scope: {},
        controller: ['$scope', 'Notifications', function($scope, Notifications) {
            $scope.notifications = Notifications;
        }]
    };
}])


.directive('searchBox', [function() {
    return {
        restrict: 'E',
        templateUrl: 'searchbox.html',
        replace: true,
        scope: {
            model: '=',
            result: '='
        },
        transclude: true,
        controller: ['$scope', function($scope) {
            if (!$scope.model.pageSize)
                $scope.model.pageSize = 10;
            if (!$scope.model.page)
                $scope.model.page = 0;
            $scope.$watch('model', function(model, oldModel) {
                if (model.page === undefined)
                    model.page = 0;
                var tempModel = angular.copy(model);
                tempModel.page = oldModel.page;
                if (angular.equals(oldModel, tempModel))
                    return;
                $scope.model.page = 0;
            }, true);
        }]
    };
}])


.directive('anyHref', ['$location', function($location) {
    return {
        restrict: 'A',
        link: function(scope, elem, attrs) {
            elem.on('click.anyHref', function() {
                scope.$apply(function() {
                    $location.path(attrs.anyHref);
                });
            });
            scope.$on('$destroy', function() {
                elem.off('.anyHref');
            });
        }
    };
}])


.directive('pageTitle', ['$document', '$injector', function($document, $injector) {
    var numTitles = 0;
    var defaultTitle = $document[0].title;
    return {
        restrict: 'EA',
        link: function(scope, elem, attrs) {
            if (numTitles > 0) {
                // Don't install if there is already a title active (for nested
                // pages)
                return;
            }

            var prefix = '', suffix = '';
            if ($injector.has('pageTitlePrefix'))
                prefix = $injector.get('pageTitlePrefix');
            if ($injector.has('pageTitleSuffix'))
                suffix = $injector.get('pageTitleSuffix');

            scope.$watch(
                function() {
                    return elem.text();
                },
                function(title) {
                    $document[0].title = prefix + title + suffix;
                }
            );
            numTitles++;

            scope.$on('$destroy', function() {
                numTitles--;
                $document[0].title = defaultTitle;
            });
        }
    };
}])

;
