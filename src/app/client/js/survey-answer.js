'use strict';

angular.module('wsaa.surveyAnswers', ['ngResource', 'wsaa.admin'])


.factory('Assessment', ['$resource', function($resource) {
    return $resource('/assessment/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false }
    });
}])


.factory('Response', ['$resource', function($resource) {
    return $resource('/assessment/:assessmentId/response/:measureId.json',
            {assessmentId: '@assessmentId', measureId: '@measureId'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT' },
        history: { method: 'GET',
            url: '/assessment/:assessmentId/response/:measureId/history.json',
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
        'Notifications',
        function($scope, Assessment, Hierarchy, routeData, Editor, authz,
                 layout, $location, current, format, $filter, Notifications) {

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
            organisation: routeData.organisation
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

    $scope.setState = function(state) {
        var assessment = angular.copy($scope.assessment);
        assessment.approval = state;
        assessment.$save();
    };
    $scope.setState = function(state) {
        $scope.assessment.$save({approval: state},
            function success() {
                Notifications.set('edit', 'success', "Saved", 5000);
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save object: " + details.statusText);
            }
        );
    };

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


.controller('AssessmentImportCtrl', [
        '$scope', 'Assessment', 'Hierarchy', 'routeData', 'Editor',
        'responseAuthz', 'layout', '$location', 'Current', 'format', '$filter',
        'Notifications', '$http', '$cookies', '$timeout',
        function($scope, Assessment, Hierarchy, routeData, Editor, authz,
                 layout, $location, current, format, $filter, Notifications, 
                 $http, $cookies, $timeout) {

    $scope.survey = routeData.survey;
    $scope.hierarchies = routeData.hierarchies;
    $scope.progress = {
        isWorking: false,
        isFinished: false,
        uploadFraction: 0.0
    };
    Notifications.remove('import');
    $scope.assessment = new Assessment({
        survey: $scope.survey,
        hierarchy : null,
        title: "Aquamark Assessment Import",
        organisation: routeData.organisation
    });
    if ($scope.hierarchies.length == 1) {
        $scope.assessment.hierarchy = $scope.hierarchies[0];
    }

    var headers = {};
    var xsrfName = $http.defaults.xsrfHeaderName;
    headers[xsrfName] = $cookies.get($http.defaults.xsrfCookieName);

    var config = {
        url: '/import/assessment.json',
        maxFilesize: 50,
        paramName: "file",
        acceptedFiles: ".xls,.xlsx",
        headers: headers,
        autoProcessQueue: false
    };

    Dropzone.autoDiscover = false;
    var dropzone = new Dropzone("#dropzone", config);

    $scope.import = function() {
        if (!dropzone.files.length) {
            Notifications.set('import', 'error', "Please choose a file");
            return;
        }
        $scope.progress.isWorking = true;
        $scope.progress.isFinished = false;
        $scope.progress.uploadFraction = 0.0;
        dropzone.processQueue();
    };

    $scope.reset = function() {
        dropzone.processQueue();
    }

    dropzone.on('sending', function(file, xhr, formData) {
        formData.append('survey', $scope.survey.id);
        formData.append('organisation', $scope.assessment.organisation.id);
        formData.append('hierarchy', $scope.assessment.hierarchy.id);
        formData.append('title', $scope.assessment.title);
    });

    dropzone.on('uploadprogress', function(file, progress) {
        console.log(progress);
        $scope.progress.uploadFraction = progress / 100;
        $scope.$apply();
    });

    dropzone.on("success", function(file, response) {
        Notifications.set('import', 'success', "Import finished", 5000);
        $timeout(function() {
            $scope.progress.isFinished = true;
        }, 1000);
        $timeout(function() {
            $location.url('/survey/' + response);
        }, 5000);
    });

    dropzone.on('addedfile', function(file) {
        if (dropzone.files.length > 1)
            dropzone.removeFile(dropzone.files[0]);
    });

    dropzone.on("error", function(file, details, request) {
        var error;
        if (request) {
            error = "Import failed: " + request.statusText;
        } else {
            error = details;
        }
        dropzone.removeAllFiles();
        Notifications.set('import', 'error', error);
        $scope.progress.isWorking = false;
        $scope.progress.isFinished = false;
        $scope.$apply();
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
        transclude: true,
        controller: ['$scope', 'hotkeys', 'Current', 'responseAuthz',
                'Notifications',
                function($scope, hotkeys, current, authz, Notifications) {
            if (!$scope.response) {
                $scope.response = {
                    responseParts: [],
                    comment: null
                };
            }
            if (!$scope.response.responseParts)
                $scope.response.responseParts = [];

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

            hotkeys.bindTo($scope)
                .add({
                    combo: ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
                    description: "Choose the Nth option for the active response part",
                    callback: function(event, hotkey) {
                        var i = Number(String.fromCharCode(event.keyCode)) - 1;
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
                        $scope.$emit('focus-comment');
                    }
                })
                .add({
                    combo: ['esc'],
                    description: "Stop editing comment",
                    allowIn: ['TEXTAREA'],
                    callback: function(event, hotkey) {
                        $scope.$emit('blur-comment');
                    }
                });
        }],
        link: function(scope, elem, attrs) {
            scope.debug = attrs.debug !== undefined;
        }
    }
}])


;
