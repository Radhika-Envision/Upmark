'use strict';

angular.module('upmark.survey.measure', [
    'upmark.surveyQuestions', 'upmark.survey.services', 'upmark.response'])


.controller('MeasureCtrl',
        function($scope, Measure, routeData, Editor, Authz,
                 $location, Notifications, Current, Program, format, layout,
                 Structure, Arrays, Response, hotkeys, $q, $timeout, $window,
                 responseTypes, ResponseType, Enqueue) {

    $scope.layout = layout;
    $scope.parent = routeData.parent;
    $scope.submission = routeData.submission;
    $scope.Response = Response;
    $scope.model = {
        response: null,
        lastSavedResponse: null,
    };

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
    $scope.newResponseType = function(type) {
        var parts;
        if (type == 'multiple_choice') {
            parts = [{type: 'multiple_choice', id: 'a', options: [
                {name: 'No', score: 0},
                {name: 'Yes', score: 1}]
            }];
        } else if (type == 'numerical') {
            parts = [{type: 'numerical', id: 'a'}];
        }

        return new ResponseType({
            obType: 'response_type',
            programId: $scope.measure.programId,
            name: $scope.measure.title,
            parts: parts,
            formula: 'a',
        });
    };
    $scope.cloneResponseType = function() {
        var rtDef = angular.copy($scope.rt.definition)
        rtDef.id = null;
        rtDef.name = rtDef.name + ' (Copy)'
        rtDef.nMeasures = 0;
        return rtDef;
    };
    $scope.rt = {
        definition: routeData.responseType || null,
        responseType: null,
        search: {
            programId: $scope.measure.programId,
            pageSize: 5,
        },
    };

    if ($scope.submission) {
        // Get the response that is associated with this measure and submission.
        // Create an empty one if it doesn't exist yet.
        $scope.lastSavedResponse = null;
        $scope.setResponse = function(response) {
            if (!response.responseParts)
                response.responseParts = [];
            $scope.model.response = response;
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
            if (!$scope.model.response.$dirty || interceptingLocation)
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
            return $scope.model.response.$save().then(
                function success(response) {
                    $scope.$broadcast('response-saved');
                    Notifications.set('edit', 'success', "Saved", 5000);
                    $scope.setResponse(response);
                    return response;
                },
                function failure(details) {
                    Notifications.set('edit', 'error',
                        "Could not save: " + details.statusText);
                    return $q.reject(details);
                });
        };
        $scope.resetResponse = function() {
            $scope.model.response = angular.copy($scope.lastSavedResponse);
        };
        $scope.toggleNotRelvant = function() {
            var oldValue = $scope.model.response.notRelevant;
            $scope.model.response.notRelevant = !oldValue;
            $scope.model.response.$save().then(
                function success(response) {
                    Notifications.set('edit', 'success', "Saved", 5000);
                    $scope.setResponse(response);
                },
                function failure(details) {
                    if (details.status == 403) {
                        Notifications.set('edit', 'info',
                            "Not saved yet: " + details.statusText);
                        if (!$scope.model.response) {
                            $scope.setResponse(nullResponse(
                                $scope.measure, $scope.submission));
                        }
                    } else {
                        $scope.model.response.notRelevant = oldValue;
                        Notifications.set('edit', 'error',
                            "Could not save: " + details.statusText);
                    }
                });
        };
        $scope.setState = function(state) {
            $scope.model.response.$save({approval: state},
                function success(response) {
                    Notifications.set('edit', 'success', "Saved", 5000);
                    $scope.setResponse(response);
                },
                function failure(details) {
                    Notifications.set('edit', 'error',
                        "Could not save: " + details.statusText);
                }
            );
        };
        $scope.$watch('response', function() {
            $scope.model.response.$dirty = !angular.equals(
                $scope.model.response, $scope.lastSavedResponse);
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
        $scope.checkRole = Authz({
            program: $scope.program,
            submission: $scope.submission,
        });
        $scope.editable = ($scope.program.isEditable &&
            !$scope.structure.deletedItem &&
            !$scope.submission && $scope.checkRole('measure_edit'));
    });

    var rtDefChanged = Enqueue(function() {
        var rtDef = $scope.rt.definition;
        if (!rtDef) {
            $scope.rt.responseType = null;
            return;
        }
        $scope.rt.responseType = new responseTypes.ResponseType(
            rtDef.name, rtDef.parts, rtDef.formula);
    }, 0, $scope);
    $scope.$watch('rt.definition', rtDefChanged);
    $scope.$watch('rt.definition', rtDefChanged, true);
    $scope.$watchGroup(['rt.responseType', 'edit.model'], function(vars) {
        var responseType = vars[0],
            measure = vars[1];
        if (!responseType || !measure || !measure.sourceVars) {
            // A measure only has source variables when viewed in the context
            // of a survey.
            return;
        }
        var measureVariables = measure.sourceVars.filter(
            function(measureVariable) {
                // Remove bindings that have not been set yet
                return measureVariable.sourceMeasure;
            }
        );
        measureVariables.forEach(function(measureVariable) {
            measureVariable.$unused = true;
        });
        responseType.unboundVars.forEach(function(targetField) {
            var measureVariable;
            for (var i = 0; i < measureVariables.length; i++) {
                var mv = measureVariables[i];
                if (mv.targetField == targetField) {
                    mv.$unused = false;
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
            withDeclaredVariables: true,
        }).$promise;
    };

    var applyRtSearch = Enqueue(function() {
        if (!$scope.rt.showSearch)
            return;
        ResponseType.query($scope.rt.search).$promise.then(
            function success(rtDefs) {
                $scope.rt.searchRts = rtDefs;
            },
            function failure(details) {
                Notifications.set('measure', 'error',
                    "Could not get response type list: " + details.statusText);
            }
        );
    }, 100, $scope);
    $scope.$watch('rt.search', applyRtSearch, true);
    $scope.$watch('rt.showSearch', applyRtSearch, true);
    $scope.chooseResponseType = function(rtDef) {
        ResponseType.get(rtDef, {
            programId: $scope.structure.program.id
        }).$promise.then(function(resolvedRtDef) {
            $scope.rt.definition = resolvedRtDef;
        });
        $scope.rt.showSearch = false;
    };

    $scope.save = function() {
        if (!$scope.edit.model)
            return;
        if (!$scope.rt.definition) {
            Notifications.set('edit', 'error',
                "Could not save: No repsonse type");
            return;
        }
        $scope.rt.definition.$createOrSave().then(
            function success(definition) {
                var measure = $scope.edit.model;
                if (measure.sourceVars) {
                    measure.sourceVars = measure.sourceVars.filter(function(mv) {
                        return !mv.$unused;
                    });
                }
                measure.responseTypeId = definition.id;
                return $scope.edit.save();
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save: " + details.statusText);
            }
        );
    };
    $scope.$on('EditSaved', function(event, model) {
        $location.url($scope.getUrl(model));
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

    $scope.getUrl = function(measure) {
        if ($scope.structure.submission) {
            return format('/2/measure/{}?submission={}',
                measure.id, $scope.structure.submission.id);
        } else {
            return format('/2/measure/{}?program={}&survey={}',
                measure.id, $scope.structure.program.id,
                $scope.structure.survey && $scope.structure.survey.id || '');
        }
    };

    $scope.getSubmissionUrl = function(submission) {
        if (submission) {
            return format('/2/measure/{}?submission={}',
                $scope.measure.id, submission.id,
                $scope.parent && $scope.parent.id || '');
        } else {
            return format('/2/measure/{}?program={}&survey={}',
                $scope.measure.id, $scope.structure.program.id,
                $scope.structure.survey && $scope.structure.survey.id || '');
        }
    };
})


.controller('MeasureListCtrl',
        function($scope, Authz, Measure, Current, layout, routeData,
            $routeParams) {

    $scope.layout = layout;
    $scope.checkRole = Authz({});
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
