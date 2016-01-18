'use strict';

angular.module('wsaa.surveyAnswers', ['ngResource', 'wsaa.admin'])


.factory('Assessment', ['$resource', 'paged', function($resource, paged) {
    return $resource('/assessment/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        }
    });
}])


.factory('Response', ['$resource', function($resource) {
    return $resource('/assessment/:assessmentId/response/:measureId.json',
            {assessmentId: '@assessmentId', measureId: '@measureId'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false },
        history: { method: 'GET',
            url: '/assessment/:assessmentId/response/:measureId/history.json',
            isArray: true, cache: false }
    });
}])


.factory('ResponseNode', ['$resource', function($resource) {
    return $resource('/assessment/:assessmentId/rnode/:qnodeId.json',
            {assessmentId: '@assessmentId', qnodeId: '@qnodeId'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT' },
        query: { method: 'GET', isArray: true, cache: false }
    });
}])


.controller('AssessmentCtrl', [
        '$scope', 'Assessment', 'Hierarchy', 'routeData', 'Editor',
        'questionAuthz', 'layout', '$location', 'Current', 'format', '$filter',
        'Notifications', 'Structure', '$http',
        function($scope, Assessment, Hierarchy, routeData, Editor, authz,
                 layout, $location, current, format, $filter, Notifications,
                 Structure, $http) {

    $scope.layout = layout;
    $scope.survey = routeData.survey;
    $scope.edit = Editor('assessment', $scope, {});
    if (routeData.assessment) {
        // Editing old
        $scope.assessment = routeData.assessment;
        $scope.children = routeData.qnodes;
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
            // Patch in survey, which is needed by Structure by is not provided
            // by the web service when requesting a list.
            $scope.assessment.hierarchy.survey = $scope.survey;
        }
        $scope.duplicate = routeData.duplicate;
        if ($scope.duplicate)
            $scope.edit.params.duplicateId = $scope.duplicate.id;
        $scope.edit.edit();
    }

    $scope.$watchGroup(['assessment', 'assessment.deleted'], function(vars) {
        var assessment = vars[0];
        if (!assessment)
            return;
        $scope.structure = Structure(assessment);
    });

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

    $scope.checkRole = authz(current, $scope.survey, $scope.assessment);

    $scope.download = function(assessment_id, export_type) {
        var url = null;
        if (export_type == 'structure')
            url = '/export/assessment/' + assessment_id + '.xlsx';
        else
            url = '/export/response/' + assessment_id + '.xlsx';

        // console.log(assessment_id, export_type);
        $http.get(url, { responseType: "arraybuffer", cache: false }).then(
            function success(response) {
                var message = "Export finished";
                Notifications.set('export', 'info', message, 5000);
                console.log(response);
                var blob = new Blob(
                    [response.data], {type: response.headers('Content-Type')});
                var name = /filename=(.*)/.exec(
                    response.headers('Content-Disposition'))[1];
                saveAs(blob, name);
            },
            function failure(response) {
                Notifications.set('export', 'error',
                    "Error: " + response.statusText);
            }
        );
    };
}])


.controller('AssessmentDuplicateCtrl', [
        '$scope', 'Assessment', 'routeData', 'layout', '$location',
        'Current', 'format', '$filter', 'Notifications',
        function($scope, Assessment, routeData, layout, $location,
                 Current, format, $filter, Notifications) {

    $scope.layout = layout;
    $scope.survey = routeData.survey;
    $scope.organisation = routeData.organisation;
    $scope.assessments = null;

    $scope.search = {
        term: "",
        trackingId: $scope.survey.trackingId,
        organisationId: $scope.organisation.id,
        approval: 'draft',
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        Assessment.query(search).$promise.then(function(assessments) {
            $scope.assessments = assessments;
        });
    }, true);
    $scope.cycleApproval = function() {
        var states = ['draft', 'final', 'reviewed', 'approved'];
        var i = states.indexOf($scope.search.approval);
        if (i >= states.length - 1)
            i = -1;
        $scope.search.approval = states[i + 1];
    };
}])


.controller('AssessmentImportCtrl', [
        '$scope', 'Assessment', 'Hierarchy', 'routeData', 'Editor',
        'questionAuthz', 'layout', '$location', 'Current', 'format', '$filter',
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
        title: "AMCV Submission Import",
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
            response: '=model',
            weight: '=',
            readonly: '='
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
