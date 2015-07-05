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
    Notifications.prototype.set = function(id, type, body, duration) {
        var newMessage = {
            id: id,
            type: type,
            css: type == 'error' ? 'danger' : type,
            body: body
        };
        this.remove(id);
        this.messages = [newMessage].concat(this.messages);
        if (type == 'error')
            log.error(body);
        else
            log.info(body);

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


/**
 * Manages state for a modal editing session.
 */
.factory('Editor', [
        '$parse', 'log', '$filter', 'Notifications', '$q',
         function($parse, log, $filter, Notifications, $q) {

    function Editor(targetPath, scope) {
        this.model = null;
        this.scope = scope;
        this.getter = $parse(targetPath);
        this.saving = false;
    };

    Editor.prototype.edit = function() {
        log.debug("Creating edit object");
        this.model = angular.copy(this.getter(this.scope));
    };

    Editor.prototype.cancel = function() {
        this.model = null;
        Notifications.remove('edit');
    };

    Editor.prototype.save = function() {
        this.scope.$broadcast('show-errors-check-validity');

        var that = this;
        var success = function(model, getResponseHeaders) {
            try {
                log.debug("Success");
                that.getter.assign(that.scope, model);
                that.model = null;
                that.scope.$emit('EditSaved', model);
                Notifications.set('edit', 'success', "Saved", 5000);
            } finally {
                that.saving = false;
                that = null;
            }
        };
        var failure = function(details) {
            try {
                that.scope.$emit('EditError');
                Notifications.set('edit', 'error',
                    "Could not save object: " + details.statusText);
            } finally {
                that.saving = false;
                that = null;
                return $q.reject(details);
            }
        };

        if (!this.model.id) {
            log.info("Saving as new entry");
            this.model.$create(success, failure);
        } else {
            log.info("Saving over old entry");
            this.model.$save(success, failure);
        }
        this.saving = true;
        Notifications.set('edit', 'info', "Saving");
    };

    Editor.prototype.destroy = function() {
        this.cancel();
        this.scope = null;
        this.getter = null;
    };

    return function(targetPath, scope) {
        log.debug('Creating editor');
        var editor = new Editor(targetPath, scope);
        scope.$on('$destroy', function() {
            editor.destroy();
            editor = null;
        });
        return editor;
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
