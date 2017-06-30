'use strict'

angular.module('vpac.widgets.form-controls', [])


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


.directive('orderedButtons', function(Enqueue) {
    return {
        restrict: 'E',
        require: 'ngModel',
        scope: {
            mode: '=',
            setValue: '&',
        },
        controller: function($scope) {
            this.scope = $scope;
            $scope.items = [];
            $scope.add = function(item) {
                $scope.items.unshift(item);
                $scope.orderChanged();
            };
            $scope.remove = function(item) {
                var i = $scope.items.indexOf(item);
                $scope.items.splice(i, 1);
                $scope.orderChanged();
            };
            $scope.orderChanged = Enqueue(function() {
                $scope._orderChanged();
            }, 0, $scope);
        },
        link: function(scope, elem, attrs, ngModel) {
            elem.toggleClass("btn-group btn-group-justified", true);

            scope.setActive = function(item, $event) {
                if (scope.setValue)
                    scope.setValue({value: item.value, $event: $event});
                if ($event.isDefaultPrevented())
                    return;
                ngModel.$setViewValue(item.getIndex(), $event);
            };

            var toModelValue = function(viewValue) {
                for (var i = 0; i < scope.items.length; i++) {
                    var item = scope.items[i];
                    if (item.getIndex() == viewValue)
                        return item.value;
                }
                return undefined;
            };
            var toViewValue = function(modelValue) {
                for (var i = 0; i < scope.items.length; i++) {
                    var item = scope.items[i];
                    if (item.value == modelValue)
                        return item.getIndex();
                }
                return undefined;
            };
            var updateView = function() {
                if (scope.mode == 'gte') {
                    scope.items.forEach(function(item) {
                        item.active = item.getIndex() >= ngModel.$viewValue;
                    });
                } else {
                    scope.items.forEach(function(item) {
                        item.active = item.getIndex() == ngModel.$viewValue;
                    });
                }
            };

            scope._orderChanged = function() {
                elem.children().sort(function(a, b) {
                    var itemA = angular.element(a.children[0]).scope();
                    var itemB = angular.element(b.children[0]).scope();
                    if (!itemA || !itemB)
                        return false;
                    return itemA.getIndex() > itemB.getIndex();
                }).appendTo(elem);
                ngModel.$setViewValue(toViewValue(ngModel.$modelValue));
                updateView();
            };

            ngModel.$parsers.unshift(toModelValue);
            ngModel.$formatters.unshift(toViewValue);
            ngModel.$render = updateView;
            ngModel.$viewChangeListeners.push(updateView);
        }
    };
})


.directive('orderedButton', [function() {
    return {
        restrict: 'E',
        require: '^orderedButtons',
        transclude: true,
        templateUrl: 'ordered_button.html',
        replace: true,
        scope: {
            index: '=',
            value: '=',
        },
        link: function(scope, elem, attrs, orderedButtons) {
            scope.active = false;
            scope.getIndex = function() {
                return scope.index != null ? scope.index : scope.value;
            };
            orderedButtons.scope.add(scope);
            scope.$on('$destroy', function() {
                orderedButtons.scope.remove(scope);
            });
            scope.$watch('index', function() {
                orderedButtons.scope.orderChanged();
            });
            scope.setActive = function($event) {
                orderedButtons.scope.setActive(scope, $event);
            };
        }
    };
}])


.directive('deleteButton', [function() {
    return {
        restrict: 'E',
        templateUrl: 'delete_button.html',
        replace: true,
        scope: {
            model: '=',
            edit: '=editor'
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


/**
 * Watches a named form (by ID) for changes; when the form becomes dirty, the
 * button this is applied to changes CSS classes to be highlighted.
 */
.directive('formSaveButton', [function() {
    return {
        restrict: 'A',
        scope: {
            target: '@formSaveButton'
        },
        link: function(scope, elem, attrs) {
            scope.$watch(
                function watch() {
                    var tElem = $('#' + scope.target);
                    // Ignore if element is missing - this can happen if the
                    // form is inside a disabled ng-if, etc.
                    if (!tElem.length)
                        return false;
                    var tField = tElem.attr('name');
                    return tElem.scope()[tField].$dirty;
                }, function(dirty) {
                    elem.toggleClass('btn-primary btn-alert', dirty);
                    elem.toggleClass('btn-default', !dirty);
                }
            );
        }
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
        }],
        link: function(scope, elem, attrs) {
            if (attrs.focusInit !== undefined)
                elem.find('input').focus();
        }
    };
}])


;
