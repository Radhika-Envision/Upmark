'use strict'

angular.module('upmark.notifications', [
   'vpac.utils'])


.factory('Notifications', ['log', '$timeout', 'Arrays',
        function(log, $timeout, Arrays) {
    function Notifications() {
        this.messages = [];
    };
    Notifications.prototype.set = function(id, type, body, duration) {
        var i = Arrays.indexOf(this.messages, id, 'id', null);
        var message;
        if (i >= 0) {
            message = this.messages[i];
        } else {
            message = {};
            this.messages.splice(0, 0, message);
        }

        message.id = id;
        message.type = type;
        message.css = type == 'error' ? 'danger' : type;
        message.body = body;
        if (message.timeout)
            $timeout.cancel(message.timeout);

        if (type == 'error')
            log.error(body);
        else
            log.info(body);

        if (duration) {
            message.timeout = $timeout(function(that, id) {
                that.remove(id);
            }, duration, true, this, id);
        }
    };
    /**
     * Remove all messages that match the given ID or object.
     */
    Notifications.prototype.remove = function(id) {
        var i = Arrays.indexOf(this.messages, id, 'id', null);
        if (i >= 0) {
            this.messages.splice(i, 1);
        }
    };
    return new Notifications();
}])


.directive('errorHeader', function() {
    return {
        restrict: 'A',
        scope: {
            errorNode: '=',
        },
        templateUrl: '/error_header.html',
        link: function(scope, elem, attrs) {
            elem.addClass('subheader bg-warning');
            scope.$watch('errorNode.error', function(error) {
                elem.toggleClass('ng-hide', !error);
            });
        }
    };
})


;
