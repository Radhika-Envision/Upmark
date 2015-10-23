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


.factory('checkLogin', ['$q', 'User', '$cookies', '$http',
         function($q, User, $cookies, $http) {
    return function checkLogin() {
        var user = $cookies.get('user');
        var xsrf = $cookies.get($http.defaults.xsrfCookieName);
        if (!user || !xsrf)
            return $q.reject("Session cookies are not defined");

        return User.get({id: 'current'}).$promise;
    };
}])


/**
 * Manages state for a modal editing session.
 */
.factory('Editor', [
        '$parse', 'log', 'Notifications', '$q', 'checkLogin',
         function($parse, log, Notifications, $q, checkLogin) {

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
            var normalError = function() {
                Notifications.set('edit', 'error',
                    "Could not save object: " + details.statusText);
            };
            var loginError = function() {
                Notifications.set('edit', 'error',
                    "Could not save object: your session has expired.");
            };
            try {
                that.scope.$emit('EditError');
                if (details.status == 403) {
                    checkLogin().then(normalError, loginError);
                } else {
                    normalError();
                }
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
            var normalError = function() {
                Notifications.set('edit', 'error',
                    "Could not delete object: " + details.statusText);
            };
            var loginError = function() {
                Notifications.set('edit', 'error',
                    "Could not delete object: your session has expired.");
            };
            try {
                that.scope.$emit('EditError');
                if (details.status == 403) {
                    checkLogin().then(normalError, loginError);
                } else {
                    normalError();
                }
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
        this.model = null;
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
        require: '?ngModel',
        link: function(scope, elem, attrs, ngModel) {
            var resize = function() {
                // Resize to something small first in case we should shrink -
                // otherwise scrollHeight will be wrong.
                elem.css('height', '10px');
                var height = elem[0].scrollHeight;
                height += elem.outerHeight() - elem.innerHeight();
                elem.css('height', '' + height + 'px');
            };

//            elem.on('input change propertychange', resize);
            scope.$watch(function() {return ngModel.$viewValue; }, resize);

            scope.$on('$destroy', function() {
                elem.off();
                elem = null;
            });
        }
    };
}])


/**
 * Takes its height from a child element. This allows CSS transitions to be used
 * for the natural height of the element.
 */
.directive('surrogateHeight', [function() {
    return {
        restrict: 'AC',
        controller: [function() {}],
        require: 'surrogateHeight',
        link: function(scope, elem, attrs, surrogateHeight) {
            surrogateHeight.update = function(height) {
                elem.height(height);
            };
            if (attrs.surrogateHeight != '')
                elem.height(Number(attrs.surrogateHeight));
        }
    };
}])


.directive('surrogateHeightTarget', [function() {
    return {
        restrict: 'AC',
        require: '^surrogateHeight',
        link: function(scope, elem, attrs, surrogateHeight) {
            scope.$watch(function() {
                return elem[0].scrollHeight;
            }, function(height) {
                surrogateHeight.update(height);
            });
        }
    };
}])


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


/**
 * Specialisation of angular-list-match-patch for lists of numbers.
 */
.directive('pathDiff', function() {
    return {
        restrict: 'AC',
        scope: {
            left: '=leftObj',
            right: '=rightObj'
        },
        link: function(scope, elem, attrs) {
            var sanitise = function(text) {
                var pattern_amp = /&/g;
                var pattern_lt = /</g;
                var pattern_gt = />/g;
                return text.replace(pattern_amp, '&amp;')
                        .replace(pattern_lt, '&lt;')
                        .replace(pattern_gt, '&gt;');
            };

            var createHtml = function(left, right) {
                if (!angular.isString(left))
                    left = '';
                if (!angular.isString(right))
                    right = '';
                var left = sanitise(left);
                var right = sanitise(right);

                var leftArr = left.split('.');
                var rightArr = right.split('.');
                var nitems = Math.max(leftArr.length, rightArr.length);
                var html = '';
                for (var i = 0; i < nitems; i++) {
                    var leftComponent = leftArr[i];
                    var rightComponent = rightArr[i];
                    var pad = i > 0 ? ' ' : '';
                    if (!leftComponent && !rightComponent) {
                        // Skip empty path element.
                    } else if (!leftComponent) {
                        html += '<ins>' + pad + rightComponent + '.</ins>';
                    } else if (!rightComponent) {
                        html += '<del>' + pad + leftComponent + '.</del>';
                    } else if (leftComponent != rightComponent) {
                        html += '<del>' + pad + leftComponent + '.</del>';
                        html += '<ins>' + pad + rightComponent + '.</ins>';
                    } else {
                        html += pad + rightComponent + '.';
                    }
                }
                return html;
            };

            var listener = function(vals) {
                elem.html(createHtml(vals[0], vals[1]));
            };

            scope.$watchGroup(['left', 'right'], listener);
        }
    };
})


.directive('markdownEditor', [function() {
    function postLink(scope, elem, attrs, ngModel) {
        scope.model = {
            mode: 'rendered',
            viewValue: null
        };

        scope.options = {
            placeholder: {text: ""},
            buttons: [
                "bold", "italic", "anchor", "image",
                "header1", "header2", "quote",
                "orderedlist", "unorderedlist",
                "removeFormat"],
            imageDragging: false
        };
        scope.$watch('placeholder', function(placeholder) {
            scope.options.placeholder.text = placeholder;
        });

        // View to model
        ngModel.$parsers.unshift(function (inputValue) {
            if (scope.model.mode == 'rendered')
                return domador(inputValue);
            else
                return inputValue;
        });

        // Model to view
        ngModel.$formatters.unshift(function (inputValue) {
            if (scope.model.mode == 'rendered')
                return megamark(inputValue);
            else
                return inputValue;
        });

        ngModel.$render = function render() {
            scope.model.viewValue = ngModel.$viewValue;
        };

        scope.$watch('model.viewValue', function(viewValue) {
            ngModel.$setViewValue(viewValue);
        });

        scope.cycleModes = function() {
            if (scope.model.mode == 'rendered')
                scope.model.mode = 'markdown';
            else
                scope.model.mode = 'rendered';
        };

        scope.$watch('model.mode', function(mode) {
            // Undocumented hack: change the model value to anything else; this
            // value is ignored but it runs the formatters.
            // http://stackoverflow.com/a/28924657/320036
            if (ngModel.$modelValue == 'bar')
                ngModel.$modelValue = 'foo';
            else
                ngModel.$modelValue = 'bar';
        });

        attrs.$observe('markdownEditorFocusOn', function(focusOn) {
            elem.find('> [medium-editor], > textarea')
                .attr('focus-on', focusOn);
        });
        attrs.$observe('markdownEditorBlurOn', function(blurOn) {
            elem.find('> [medium-editor], > textarea')
                .attr('blur-on', blurOn);
        });
    };

    return {
        restrict: 'E',
        scope: {
            placeholder: '='
        },
        templateUrl: 'markdown_editor.html',
        require: 'ngModel',
        compile: function compile(tElem, tAttrs) {
            tElem.find('> [medium-editor], > textarea')
                .attr('focus-on', tAttrs.markdownEditorFocusOn);
            tElem.find('> [medium-editor], > textarea')
                .attr('blur-on', tAttrs.markdownEditorBlurOn);

            return postLink;
        }
    };
}])


.service('docsService', [function() {
    this.add = null;
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
        template: '<h3 ng-show="ndocs > 0">Documentation</h3>' +
                  '<ul class="docs fa-ul fa-ul-big"></ul>',
        link: function(scope, elem, attrs) {
            scope.ndocs = 0;
            docsService.add = function(transcludeElem) {
                var container = elem.children('ul.docs');
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


.directive('formNavWarn', [function() {
    return {
        restrict: 'AC',
        require: 'form',
        link: function(scope, elem, attrs, form) {
            scope.$on('$locationChangeStart', function(event) {
                if (form.$dirty) {
                    var answer = confirm("You have unsaved changes. Are you" +
                        "sure you want to leave this page?");
                    if (!answer) {
                        event.preventDefault();
                    }
                }
            });
        }
    };
}])

;
