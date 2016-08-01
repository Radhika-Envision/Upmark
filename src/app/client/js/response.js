'use strict';

angular.module('wsaa.response', ['ngResource', 'wsaa.admin'])


.directive('response', [function() {
    return {
        restrict: 'E',
        scope: {
            responseType: '=type',
            response: '=model',
            weight: '=',
            readonly: '=',
            hasQuality: '='
        },
        replace: true,
        templateUrl: 'response.html',
        transclude: true,
        controller: ['$scope', 'hotkeys', 'Current', 'questionAuthz',
                'Notifications', 'Enqueue',
                function($scope, hotkeys, current, authz, Notifications,
                    Enqueue) {
            $scope.$watch('response', function(response) {
                if (!$scope.response) {
                    $scope.response = {
                        responseParts: [],
                        comment: ''
                    };
                }
            });
            if ($scope.weight == null)
                $scope.weight = 100;

            $scope.stats = {
                expressionVars: null,
                score: 0.0
            };
            $scope.state = {
                active: 0
            };

            $scope.choose = function(iPart, iOpt, note) {
                var parts = angular.copy($scope.response.responseParts);
                parts[iPart] = {
                    index: iOpt,
                    note: $scope.responseType.parts[iPart].options[iOpt].name
                };
                $scope.response.responseParts = parts;
                var nParts = $scope.responseType.parts.length;
                $scope.state.active = Math.min(iPart + 1, nParts - 1);
            };
            $scope.active = function(iPart, iOpt) {
                var partR = $scope.response.responseParts[iPart];
                if (partR)
                    return partR.index == iOpt;
                return false;
            };
            $scope.getActiveOption = function(iPart) {
                if (!$scope.response.responseParts.length)
                    return null;
                return $scope.response.responseParts[iPart];
            };
            $scope.enabled = function(iPart, iOpt) {
                if (!$scope.stats.expressionVars)
                    return false;
                var responseType = $scope.responseType;
                var partT = responseType.parts[iPart];
                var option = partT.options[iOpt];
                if (!option['if'])
                    return true;
                var isEnabled;
                try {
                    var exp = Parser.parse(option['if']);
                    isEnabled = exp.evaluate($scope.stats.expressionVars);
                } catch (e) {
                    if ($scope.debug) {
                        Notifications.set('response', 'warning',
                            "Condition: " + e.message);
                    }
                    throw e;
                }

                Notifications.remove('response');
                return isEnabled;
            };

            $scope.updateDocs = Enqueue(function() {
                var parts = $scope.responseType.parts;
                if (!parts) {
                    $scope.docs = [];
                    return;
                }

                var docs = [];
                for (var i = 0; i < parts.length; i++) {
                    var part = parts[i];
                    var doc = {
                        index: i,
                        name: part.name,
                        description: part.description,
                        options: []
                    };
                    for (var j = 0; j < part.options.length; j++) {
                        var opt = part.options[j];
                        if (opt.description) {
                            doc.options.push({
                                index: j,
                                active: $scope.active(i, j),
                                name: opt.name,
                                description: opt.description
                            });
                        }
                    }
                    if (doc.description || doc.options.length)
                        docs.push(doc);
                }
                $scope.docs = docs;
            });
            $scope.$watch('responseType.parts', function(parts) {
                $scope.updateDocs();
            }, true);
            $scope.$watch('response.responseParts', function(parts) {
                $scope.updateDocs();
            });

            $scope.$watch('responseType.parts.length', function(length) {
                $scope.response.responseParts = $scope.response.responseParts
                    .slice(0, length);
            });

            $scope.$watchGroup(['responseType', 'response.responseParts',
                    'responseType.formula'], function(vals) {
                // Calculate score
                var responseType = vals[0];
                var responseParts = vals[1];
                if (!responseType || !responseParts)
                    return;

                var expressionVars = {};
                var score = 0.0;
                for (var i = 0; i < responseType.parts.length; i++) {
                    var partT = responseType.parts[i];
                    var partR = responseParts[i];
                    if (partR && partR.index != null) {
                        var option = partT.options[partR.index];
                        if (partT.id) {
                            expressionVars[partT.id] = option.score;
                            expressionVars[partT.id + '__i'] = partR.index;
                        }
                        score += option.score;
                    } else {
                        if (partT.id) {
                            expressionVars[partT.id] = 0.0;
                            expressionVars[partT.id + '__i'] = -1;
                        }
                    }
                }
                if (responseType.formula) {
                    try {
                        var exp = Parser.parse(responseType.formula);
                        score = exp.evaluate(expressionVars);
                    } catch (e) {
                        if ($scope.debug) {
                            Notifications.set('response', 'warning',
                                "Formula: " + e.message);
                        }
                        throw e;
                    }
                    Notifications.remove('response');
                }
                $scope.stats = {
                    expressionVars: expressionVars,
                    score: $scope.response.notRelevant ? 0 : score
                };
            });

            $scope.checkRole = authz(current, $scope.survey);

            hotkeys.bindTo($scope)
                .add({
                    combo: ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
                    description: "Choose the Nth option for the active response part",
                    callback: function(event, hotkey) {
                        var i = Number(String.fromCharCode(event.which)) - 1;
                        i = Math.max(0, i);
                        i = Math.min($scope.responseType.parts.length, i);
                        $scope.choose($scope.state.active, i);
                    }
                })
                .add({
                    combo: ['-', '_'],
                    description: "Previous response part",
                    callback: function(event, hotkey) {
                        $scope.state.active = Math.max(
                            0, $scope.state.active - 1);
                    }
                })
                .add({
                    combo: ['+', '='],
                    description: "Next response part",
                    callback: function(event, hotkey) {
                        $scope.state.active = Math.min(
                            $scope.responseType.parts.length - 1,
                            $scope.state.active + 1);
                    }
                })
                .add({
                    combo: ['c'],
                    description: "Edit comment",
                    callback: function(event, hotkey) {
                        event.stopPropagation();
                        event.preventDefault();
                        $scope.$broadcast('focus-comment');
                    }
                })
                .add({
                    combo: ['esc'],
                    description: "Stop editing comment",
                    allowIn: ['TEXTAREA'],
                    callback: function(event, hotkey) {
                        $scope.$broadcast('blur-comment');
                    }
                });
        }],
        link: function(scope, elem, attrs) {
            scope.debug = attrs.debug !== undefined;
        }
    }
}])


;
