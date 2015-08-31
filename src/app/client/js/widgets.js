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
                console.log('update', fraction);
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


.directive('columnProgress', [function() {
    return {
        restrict: 'E',
        scope: {
            items: '='
        },
        templateUrl: "bar-progress.html",
        controller: ['$scope', function($scope) {
            $scope.$watch('items', function(items) {
                if (!items) {
                    $scope.summary = '';
                    return;
                }
                var summary = [];
                for (var i = 0; i < items.length; i++) {
                    var item = items[i];
                    summary.push(item.name + ': ' + item.value);
                }
                $scope.summary = summary.join(', ');
            });
        }],
        link: function(scope, elem, attrs) {
            elem.on('click', function(event) {
                event.preventDefault();
                event.stopPropagation();
            });
            scope.$on('$destroy', function() {
                elem.off('click');
            });
        }
    };
}])


.directive('columnProgressColumn', [function() {
    return {
        restrict: 'A',
        link: function(scope, elem, attrs) {
            scope.$watch('item.fraction', function(fraction) {
                elem.css('height', '' + (fraction * 100) + '%');
                elem.toggleClass('complete', fraction > 0.999999);
            });
        }
    };
}])


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
        '$parse', 'log', 'Notifications', '$q',
         function($parse, log, Notifications, $q) {

    function Editor(targetPath, scope, params, resource) {
        this.model = null;
        this.scope = scope;
        this.params = params;
        this.resource = resource;
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

        if (angular.isArray(this.model)) {
            log.info("Reordering list");
            this.resource.reorder(this.params, this.model, success, failure);
        } else if (!this.model.id) {
            log.info("Saving as new entry");
            this.model.$create(this.params, success, failure);
        } else {
            log.info("Saving over old entry");
            this.model.$save(this.params, success, failure);
        }
        this.saving = true;
        Notifications.set('edit', 'info', "Saving");
    };

    Editor.prototype.del = function() {
        var that = this;
        var success = function(model, getResponseHeaders) {
            try {
                log.debug("Success");
                that.model = null;
                that.scope.$emit('EditDeleted', model);
                Notifications.set('edit', 'success', "Deleted", 5000);
            } finally {
                that.saving = false;
                that = null;
            }
        };
        var failure = function(details) {
            try {
                that.scope.$emit('EditError');
                Notifications.set('edit', 'error',
                    "Could not delete object: " + details.statusText);
            } finally {
                that.saving = false;
                that = null;
                return $q.reject(details);
            }
        };

        log.info("Deleting");
        var model = this.getter(this.scope);
        model.$delete(this.params, success, failure);

        this.saving = true;
        Notifications.set('edit', 'info', "Deleting");
    };

    Editor.prototype.destroy = function() {
        this.cancel();
        this.scope = null;
        this.getter = null;
    };

    return function(targetPath, scope, params, resource) {
        log.debug('Creating editor');
        var editor = new Editor(targetPath, scope, params, resource);
        scope.$on('$destroy', function() {
            editor.destroy();
            editor = null;
        });
        return editor;
    };
}])


.directive('emptyAsNull', function() {
    return {
        restrict: 'A',
        require: 'ngModel',
        link: function (scope, elem, attrs, ctrl) {
            function emptyToNull(viewValue) {
                if (viewValue === '')
                    return null;
                return viewValue;
            };
            ctrl.$parsers.push(emptyToNull);
            ctrl.$modelValue = emptyToNull(ctrl.$viewValue);
        }
    };
})


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


.factory('layout', function() {
    return {
        expandHeader: false
    };
})


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


.directive('autoresize', [function() {
    return {
        restrict: 'AC',
        link: function(scope, elem, attrs) {
            var resize = function() {
                // Resize to something small first in case we should shrink -
                // otherwise scrollHeight will be wrong.
                elem.css('height', '10px');
                var height = elem[0].scrollHeight;
                height += elem.outerHeight() - elem.innerHeight();
                elem.css('height', '' + height + 'px');
            };

            elem.on('input change', resize);
            scope.$watch(attrs.ngModel, resize);

            scope.$on('$destroy', function() {
                elem.off();
                elem = null;
            });
        }
    };
}])


.controller('WoofmarkTest', function($scope) {
    $scope.model = {
        contents: 'Foo *bar*'
    };
})


.directive('markdownEditor', [function() {
    return {
        restrict: 'E',
        scope: {
            markdown: '=model'
        },
        templateUrl: 'markdown_editor.html',
        controller: ['$scope', 'bind', function($scope, bind) {
            $scope.model = {
                wysiwygMode: true,
                html: null,
                markdown: null
            };

            bind($scope, 'markdown', $scope, 'model.markdown', true);

            $scope.options = {
                placeholder: {text: ""},
                buttons: [
                    "bold", "italic", "underline", "anchor",
                    "header1", "header2", "quote",
                    "orderedlist", "unorderedlist"]
            };

            $scope.$watch('model.markdown', function(markdown) {
                if (markdown == null)
                    return;
                console.log('Markdown changed')
                $scope.model.html = megamark(markdown);
            });

            $scope.$watch('model.html', function(html) {
                if (html == null)
                    return;
                console.log('HTML changed')
                $scope.model.markdown = domador(html);
            });
        }],
        link: function(scope, elem, attrs) {
            console.log('Linking markdown editor')
        }
    };
}])


.directive('mediumEditor', [function() {
    return {
        restrict: 'A',
        scope: {
            model: '=',
            options: '='
        },
        require: '?^markdownEditor',
        controller: ['$scope', function($scope) {
        }],
        link: function(scope, elem, attrs, markdownEditor) {
            console.log('Linking medium editor')
            var editor = null;

            scope.$watch('options', function(options) {
                if (editor) {
                    editor.destroy();
                    editor = null;
                }
                console.log('Creating medium editor')
                editor = new MediumEditor(elem, options);
            });

            elem.on('blur input change', function() {
                scope.$apply(function() {
                    console.log('medium changed', elem.html())
                    scope.model = elem.html();
                });
            });
            scope.$watch('model', function(model) {
                elem.html(model);
            });

            scope.$on('$destroy', function() {
                if (editor) {
                    editor.destroy();
                    editor = null;
                }
                elem.off();
                elem = null;
                scope = null;
            });
        }
    };
}])


;
