'use strict';

angular.module('wsaa.surveyAnswers', ['ngResource', 'wsaa.admin'])


.factory('Assessment', ['$resource', function($resource) {
    return $resource('/assessment/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false },
        history: { method: 'GET', url: '/assessment/:id/history.json',
            isArray: true, cache: false }
    });
}])


.factory('responseAuthz', ['Roles', function(Roles) {
    return function(current, assessment) {
        return function(functionName) {
            var ownOrg = false;
            var org = assessment && assessment.organisation || null;
            if (org)
                ownOrg = org.id == current.user.organisation.id;
            switch(functionName) {
                case 'view_aggregate_score':
                    if (Roles.hasPermission(current.user.role, 'consultant'))
                        return true;
                    return false;
                    break;
                case 'view_single_score':
                    return true;
                    break;
                case 'assessment_admin':
                    if (Roles.hasPermission(current.user.role, 'consultant'))
                        return true;
                    if (Roles.hasPermission(current.user.role, 'org-admin'))
                        return ownOrg;
                    break;
                case 'assessment_edit':
                case 'view_response':
                case 'alter_response':
                    if (Roles.hasPermission(current.user.role, 'consultant'))
                        return true;
                    if (Roles.hasPermission(current.user.role, 'clerk'))
                        return ownOrg;
                    break;
            }
            return false;
        };
    };
}])


.controller('AssessmentCtrl', [
        '$scope', 'Assessment', 'Hierarchy', 'routeData', 'Editor',
        'responseAuthz', 'layout', '$location', 'Current', 'format', '$filter',
        function($scope, Assessment, Hierarchy, routeData, Editor, authz,
                 layout, $location, current, format, $filter) {

    $scope.layout = layout;
    $scope.survey = routeData.survey;
    $scope.edit = Editor('assessment', $scope, {});
    if (routeData.assessment) {
        // Editing old
        $scope.assessment = routeData.assessment;
        $scope.qnodes = routeData.qnodes;
    } else {
        // Creating new
        $scope.assessment = new Assessment({
            survey: $scope.survey,
            organisation: routeData.organisation,
            approval: 'draft'
        });
        $scope.edit.params.surveyId = $scope.survey.id;
        $scope.edit.params.orgId = routeData.organisation.id;
        $scope.hierarchies = routeData.hierarchies;
        if ($scope.hierarchies.length == 1) {
            $scope.assessment.hierarchy = $scope.hierarchies[0];
        }
        $scope.edit.edit();
    }

    $scope.$watch('edit.model.hierarchy', function(hierarchy) {
        // Generate title first time
        if (!hierarchy || !$scope.edit.model)
            return;
        if (!$scope.edit.model.title) {
            $scope.edit.model.title = format('{} - {}',
                hierarchy.title, $filter('date')(new Date(), 'MMM yyyy'));
        }
        $scope.edit.params.hierarchyId = hierarchy.id;
    });

    $scope.$on('EditSaved', function(event, model) {
        $location.url(format(
            '/assessment/{}', model.id, $scope.survey.id));
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url(format(
            '/survey/{}', $scope.survey.id));
    });

    $scope.checkRole = authz(current, $scope.assessment);
}])


.directive('response', [function() {
    return {
        restrict: 'E',
        scope: {
            responseType: '=type',
            response: '=model'
        },
        replace: true,
        templateUrl: 'response.html',
        controller: ['$scope', 'hotkeys', 'Current', 'responseAuthz',
                'Notifications',
                function($scope, hotkeys, current, authz, Notifications) {
            if (!$scope.response) {
                $scope.response = {
                    responseParts: [],
                    comment: null
                };
            }
            $scope.stats = {
                expressionVars: null,
                score: 0.0
            };

            $scope.choose = function(iPart, iOpt, note) {
                console.log('choosing', iPart, iOpt, note)
                var parts = angular.copy($scope.response.responseParts);
                parts[iPart] = {
                    index: iOpt,
                    note: note
                };
                $scope.response.responseParts = parts;
            };
            $scope.active = function(iPart, iOpt) {
                var partR = $scope.response.responseParts[iPart];
                if (partR)
                    return partR.index == iOpt;
                return false;
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

                console.log('calculating score')
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
                    score: score
                };
            });

            $scope.checkRole = authz(current, $scope.survey);
        }],
        link: function(scope, elem, attrs) {
            scope.debug = attrs.debug !== undefined;
        }
    }
}])


;
