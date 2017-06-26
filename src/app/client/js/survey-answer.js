'use strict';

angular.module('upmark.surveyAnswers', ['ngResource', 'upmark.admin',
                                      'ui.select', 'vpac.utils'])


.directive('responseForm', function() {
    return {
        restrict: 'E',
        scope: {
            rt: '=type',
            response: '=model',
            weight_: '=weight',
            readonly: '=',
            hasQuality: '=',
            externs: '=',
            isDummy: '@',
        },
        replace: true,
        templateUrl: 'response_form.html',
        transclude: true,
        controller: ['$scope', 'hotkeys', 'Authz', 'Enqueue',
                function($scope, hotkeys, Authz, Enqueue) {
            $scope.$watch('weight_', function(weight) {
                $scope.weight = weight == null ? 100 : weight;
            });

            $scope.state = {
                variables: null,
                score: 0,
                active: 0
            };

            var recalculate = Enqueue(function() {
                if ($scope.isDummy)
                    return;
                var rt = $scope.rt,
                    partsR = $scope.response.responseParts;

                if (!rt || !partsR) {
                    $scope.state.score = 0;
                    $scope.state.active = 0;
                    $scope.state.message = 'Loading';
                    return;
                }
                rt.parts.forEach(function(part, i) {
                    if (!partsR[i])
                        partsR[i] = {};
                });

                if ($scope.response.notRelevant) {
                    $scope.state.variables = angular.merge({}, $scope.externs);
                    $scope.state.score = 0;
                } else {
                    $scope.state.variables = angular.merge(
                        {}, $scope.externs, rt.variables(partsR, true));
                    try {
                        rt.validate(partsR, $scope.state.variables);
                        $scope.state.score = rt.score(
                            partsR, $scope.state.variables);
                        $scope.state.message = null;
                    } catch (e) {
                        $scope.state.message = '' + e;
                        $scope.state.score = 0;
                    }
                }
            }, 0, $scope);
            $scope.$watch('rt', recalculate);
            $scope.$watch('response.responseParts', recalculate, true);
            $scope.$watch('externs', recalculate, true);

            $scope.getPartData = function(partSchema) {
                if ($scope.isDummy)
                    return;
                var i = $scope.rt.parts.indexOf(partSchema);
                return $scope.response.responseParts[i];
            };

            $scope.choose = function(partSchema, option) {
                var partData = $scope.getPartData(partSchema);
                partData.index = partSchema.options.indexOf(option);
                partData.note = option.name;
                var nParts = $scope.rt.parts.length;
                var iPart = $scope.rt.parts.indexOf(partSchema);
                $scope.state.active = Math.min(iPart + 1, nParts - 1);
            };
            $scope.available = function(option) {
                if (!$scope.state.variables)
                    return false;
                return option.available($scope.state.variables);
            };
            $scope.isFinite = isFinite;

            $scope.checkRole = Authz({program: $scope.program});

            hotkeys.bindTo($scope)
                .add({
                    combo: ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
                    description: "Choose the Nth option for the active response part",
                    callback: function(event, hotkey) {
                        var i = Number(String.fromCharCode(event.which)) - 1;
                        i = Math.max(0, i);
                        i = Math.min($scope.rt.parts.length, i);
                        var partSchema = $scope.rt.parts[$scope.state.active];
                        var option = partSchema.options[i];
                        $scope.choose(partSchema, option);
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
                            $scope.rt.parts.length - 1,
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
                    description: "Stop editing comment (only in plain text mode)",
                    allowIn: ['TEXTAREA'],
                    callback: function(event, hotkey) {
                        event.stopPropagation();
                        event.preventDefault();
                        $scope.$broadcast('blur-comment');
                    }
                });
        }],
        link: function(scope, elem, attrs) {
            scope.debug = attrs.debug !== undefined;
        }
    }
                                      })


.factory('Response', ['$resource', function($resource) {
    return $resource('/submission/:submissionId/response/:measureId.json',
            {submissionId: '@submissionId', measureId: '@measureId'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false },
        history: { method: 'GET',
            url: '/submission/:submissionId/response/:measureId/history.json',
            isArray: true, cache: false }
    });
}])


.factory('ResponseNode', ['$resource', function($resource) {
    return $resource('/submission/:submissionId/rnode/:qnodeId.json',
            {submissionId: '@submissionId', qnodeId: '@qnodeId'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false }
    });
}])

;
