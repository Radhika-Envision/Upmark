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


.factory('Notifications', ['log', function(log) {
    function Notifications() {
        this.messages = [];
    };
    Notifications.prototype.add = function(id, type, body) {
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
        this.messages = this.messages.concat(newMessage);
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

;
