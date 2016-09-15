'use strict';

angular.module('wsaa.survey.measure', [
    'wsaa.surveyQuestions', 'wsaa.survey.services', 'wsaa.response'])


.controller('MeasureCtrl',
        function($scope, Measure, routeData, Editor, questionAuthz,
                 $location, Notifications, Current, Program, format, layout,
                 Structure, Arrays, Response, hotkeys, $q, $timeout, $window,
                 responseTypes, ResponseType) {

     $scope.newResponseType = function(programId) {
         return new ResponseType({
             programId: programId,
             name: null,
             parts: [{type: 'multiple_choice', id: 'a', options: [
                 {name: 'No', score: 0},
                 {name: 'Yes', score: 1}]
             }],
             formula: null,
         });
     };

    $scope.layout = layout;
    $scope.parent = routeData.parent;
    $scope.submission = routeData.submission;

    if (routeData.measure) {
        // Editing old
        $scope.measure = routeData.measure;
    } else {
        // Creating new
        $scope.measure = new Measure({
            obType: 'measure',
            parent: routeData.parent,
            programId: routeData.program.id,
            weight: 100,
            responseTypeId: null,
            sourceVars: [],
        });
    }
    $scope.rt = {
        definition: routeData.responseType ||
            $scope.newResponseType($scope.measure.programId),
        responseType: null,
    };

    if ($scope.submission) {
        // Get the response that is associated with this measure and submission.
        // Create an empty one if it doesn't exist yet.
        $scope.lastSavedResponse = null;
        $scope.setResponse = function(response) {
            if (!response.responseParts)
                response.responseParts = [];
            $scope.response = response;
            $scope.lastSavedResponse = angular.copy(response);
        };

        var nullResponse = function(measure, submission) {
            return new Response({
                measureId: $scope.measure ? $scope.measure.id : null,
                submissionId: $scope.submission ? $scope.submission.id : null,
                responseParts: [],
                comment: '',
                notRelevant: false,
                approval: 'draft'
            });
        };
        $scope.setResponse(nullResponse());
        Response.get({
            measureId: $scope.measure.id,
            submissionId: $scope.submission.id
        }).$promise.then(
            function success(response) {
                $scope.setResponse(response);
            },
            function failure(details) {
                if (details.status != 404) {
                    Notifications.set('edit', 'error',
                        "Failed to get response details: " + details.statusText);
                    return;
                }
                $scope.setResponse(nullResponse(
                    $scope.measure, $scope.submission));
            }
        );

        var interceptingLocation = false;
        $scope.$on('$locationChangeStart', function(event, next, current) {
            if (!$scope.response.$dirty || interceptingLocation)
                return;
            event.preventDefault();
            interceptingLocation = true;
            $scope.saveResponse().then(
                function success() {
                    $window.location.href = next;
                    $timeout(function() {
                        interceptingLocation = false;
                    });
                },
                function failure(details) {
                    var message = "Failed to save: " +
                        details.statusText +
                        ". Are you sure you want to leave this page?";
                    var answer = confirm(message);
                    if (answer)
                        $window.location.href = next;
                    $timeout(function() {
                        interceptingLocation = false;
                    });
                }
            );
        });

        $scope.saveResponse = function() {
            return $scope.response.$save().then(
                function success(response) {
                    $scope.$broadcast('response-saved');
                    Notifications.set('edit', 'success', "Saved", 5000);
                    $scope.setResponse(response);
                    return response;
                },
                function failure(details) {
                    Notifications.set('edit', 'error',
                        "Could not save response: " + details.statusText);
                    return $q.reject(details);
                });
        };
        $scope.resetResponse = function() {
            $scope.response = angular.copy($scope.lastSavedResponse);
        };
        $scope.toggleNotRelvant = function() {
            var oldValue = $scope.response.notRelevant;
            $scope.response.notRelevant = !oldValue;
            $scope.response.$save().then(
                function success(response) {
                    Notifications.set('edit', 'success', "Saved", 5000);
                    $scope.setResponse(response);
                },
                function failure(details) {
                    if (details.status == 403) {
                        Notifications.set('edit', 'info',
                            "Not saved yet: " + details.statusText);
                        if (!$scope.response) {
                            $scope.setResponse(nullResponse(
                                $scope.measure, $scope.submission));
                        }
                    } else {
                        $scope.response.notRelevant = oldValue;
                        Notifications.set('edit', 'error',
                            "Could not save response: " + details.statusText);
                    }
                });
        };
        $scope.setState = function(state) {
            $scope.response.$save({approval: state},
                function success(response) {
                    Notifications.set('edit', 'success', "Saved", 5000);
                    $scope.setResponse(response);
                },
                function failure(details) {
                    Notifications.set('edit', 'error',
                        "Could not save response: " + details.statusText);
                }
            );
        };
        $scope.$watch('response', function() {
            $scope.response.$dirty = !angular.equals(
                $scope.response, $scope.lastSavedResponse);
        }, true);
    }

    $scope.$watch('measure', function(measure) {
        $scope.structure = Structure(measure, $scope.submission);
        $scope.program = $scope.structure.program;
        $scope.edit = Editor('measure', $scope, {
            parentId: measure.parent && measure.parent.id,
            surveyId: measure.parent && measure.parent.survey.id,
            programId: $scope.program.id
        });
        if (!measure.id)
            $scope.edit.edit();

        if (measure.parents) {
            var parents = [];
            for (var i = 0; i < measure.parents.length; i++) {
                parents.push(Structure(measure.parents[i]));
            }
            $scope.parents = parents;
        }
    });
    $scope.$watch('structure.program', function(program) {
        $scope.checkRole = questionAuthz(Current, $scope.program, $scope.submission);
        $scope.editable = ($scope.program.isEditable &&
            !$scope.structure.deletedItem &&
            !$scope.submission && $scope.checkRole('measure_edit'));
    });

    $scope.$watch('rt.definition', function(rtDef) {
        $scope.rt.responseType = new responseTypes.ResponseType(
            rtDef.name, rtDef.parts, rtDef.formula);
    }, true);
    $scope.$watchGroup(['rt.responseType', 'edit.model'], function(vars) {
        var responseType = vars[0],
            measure = vars[1];
        if (!responseType || !measure)
            return;
        var measureVariables = measure.sourceVars.filter(
            function(measureVariable) {
                // Remove bindings that have not been set yet
                return measureVariable.sourceMeasure;
            }
        );
        measureVariables.forEach(function(measureVariable) {
            measureVariable.unused = true;
        });
        responseType.unboundVars.forEach(function(targetField) {
            var measureVariable;
            for (var i = 0; i < measureVariables.length; i++) {
                var mv = measureVariables[i];
                if (mv.targetField == targetField) {
                    mv.unused = false;
                    return;
                }
            }
            measureVariables.push({
                targetField: targetField,
                sourceMeasure: null,
                sourceField: null,
            });
        });
        measureVariables.sort(function(a, b) {
            return a.targetField.localeCompare(b);
        });
        measure.sourceVars = measureVariables;
    });
    $scope.searchMeasuresToBind = function(term) {
        return Measure.query({
            term: term,
            programId: $scope.structure.program.id,
            surveyId: $scope.structure.survey.id,
            withResponseTypes: true,
        }).$promise;
    };
    $scope.measureBound = function(item, model) {
        var rtDef = item.responseType;
        item.$responseType = new responseTypes.ResponseType(
            rtDef.name, rtDef.parts, rtDef.formula);
    };

    $scope.save = function() {
        if (!$scope.edit.model)
            return;
        $scope.rt.definition.$createOrSave().then(
            function success(definition) {
                $scope.edit.model.responseTypeId = definition.id;
                return $scope.edit.save();
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save response type: " + details.statusText);
            }
        );
    };
    $scope.$on('EditSaved', function(event, model) {
        if (model.survey) {
            $location.url(format(
                '/2/measure/{}?program={}&survey={}', model.id, model.programId,
                model.survey.id));
        } else {
            $location.url(format(
                '/2/measure/{}?program={}', model.id, model.programId));
        }
    });
    $scope.$on('EditDeleted', function(event, model) {
        if (model.parent) {
            $location.url(format(
                '/2/qnode/{}?program={}', model.parent.id, model.programId));
        } else {
            $location.url(format(
                '/2/measures?program={}', model.programId));
        }
    });

    $scope.Measure = Measure;

    if ($scope.submission) {
        var t_approval;
        if (Current.user.role == 'clerk' || Current.user.role == 'org_admin')
            t_approval = 'final';
        else if (Current.user.role == 'consultant')
            t_approval = 'reviewed';
        else
            t_approval = 'approved';
        hotkeys.bindTo($scope)
            .add({
                combo: ['ctrl+enter'],
                description: "Save the response, and mark it as " + t_approval,
                callback: function(event, hotkey) {
                    $scope.setState(t_approval);
                }
            });
    }

    $scope.getSubmissionUrl = function(submission) {
        if (submission) {
            return format('/2/measure/{}?submission={}',
                $scope.measure.id, submission.id,
                $scope.parent && $scope.parent.id || '');
        } else {
            return format('/2/measure/{}?program={}&survey={}',
                $scope.measure.id, $scope.structure.program.id,
                $scope.structure.survey.id || '');
        }
    };
})


.controller('MeasureListCtrl',
        function($scope, questionAuthz, Measure, Current, layout, routeData,
            $routeParams) {

    $scope.layout = layout;
    $scope.checkRole = questionAuthz(Current, null);
    $scope.program = routeData.program;

    $scope.search = {
        term: $routeParams.initialTerm || "",
        programId: $scope.program && $scope.program.id,
        orphan: null,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        Measure.query(search).$promise.then(function(measures) {
            $scope.measures = measures;
        });
    }, true);

    $scope.cycleOrphan = function() {
        switch ($scope.search.orphan) {
            case true:
                $scope.search.orphan = null;
                break;
            case null:
                $scope.search.orphan = false;
                break;
            case false:
                $scope.search.orphan = true;
                break;
        }
    };
})


;
