'use strict';

angular.module('wsaa.survey.measure', [
    'wsaa.surveyQuestions', 'wsaa.survey.services'])


.controller('MeasureCtrl',
        function($scope, Measure, routeData, Editor, questionAuthz,
                 $location, Notifications, Current, Program, format, layout,
                 Structure, Arrays, Response, hotkeys, $q, $timeout, $window,
                 responseTypes) {

    $scope.layout = layout;
    $scope.parent = routeData.parent;
    $scope.submission = routeData.submission;

    if (routeData.measure) {
        // Editing old
        $scope.measure = routeData.measure;
    } else {
        // Creating new
        $scope.measure = new Measure({
            parent: routeData.parent,
            program: routeData.program,
            weight: 100,
            responseType: null
        });
    }

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
            parentId: $scope.parent && $scope.parent.id,
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
        // Do a little processing on the response types
        if (!program.responseTypes)
            return;
        var responseType = null;
        var responseTypes = angular.copy(program.responseTypes);
        for (var i = 0; i < responseTypes.length; i++) {
            var t = responseTypes[i];
            if (t.parts.length == 0) {
                t.description = "No parts";
            } else {
                if (t.parts.length == 1) {
                    t.description = "1 part";
                } else {
                    t.description = "" + t.parts.length + " parts";
                }
                var optNames = null;
                if (t.parts[0].type == 'multiple_choice') {
                    optNames = t.parts[0].options.map(function(o) {
                        return o.name;
                    }).filter(function(n) {
                        return !!n;
                    }).join(', ');
                }
                if (optNames)
                    t.description += ': ' + optNames;
                if (t.parts.length > 1)
                    t.description += ' etc.';
            }
        }
        $scope.responseTypes = responseTypes;

        $scope.checkRole = questionAuthz(Current, $scope.program, $scope.submission);
        $scope.editable = ($scope.program.isEditable &&
            !$scope.structure.deletedItem &&
            !$scope.submission && $scope.checkRole('measure_edit'));
    });
    $scope.$watchGroup(['measure.responseType', 'structure.program.responseTypes'],
                       function(vars) {
        var rtId = vars[0];
        var rts = vars[1];
        var i = Arrays.indexOf(rts, rtId, 'id', null);
        $scope.responseType = new responseTypes.ResponseType(rts[i]);
    });

    $scope.$on('EditSaved', function(event, model) {
        if (model.parent) {
            $location.url(format(
                '/1/measure/{}?program={}&parent={}', model.id, $scope.program.id,
                $scope.parent.id));
        } else {
            $location.url(format(
                '/1/measure/{}?program={}', model.id, $scope.program.id));
        }
    });
    $scope.$on('EditDeleted', function(event, model) {
        if (model.parent) {
            $location.url(format(
                '/1/qnode/{}?program={}', model.parent.id, $scope.program.id));
        } else {
            $location.url(format(
                '/1/measures?program={}', $scope.program.id));
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
            return format('/1/measure/{}?submission={}',
                $scope.measure.id, submission.id,
                $scope.parent && $scope.parent.id || '');
        } else {
            return format('/1/measure/{}?program={}&parent={}',
                $scope.measure.id, $scope.program.id,
                $scope.measure.parent && $scope.measure.parent.id || '');
        }
    };
})


.controller('MeasureListCtrl', ['$scope', 'questionAuthz', 'Measure', 'Current',
        'layout', 'routeData',
        function($scope, authz, Measure, current, layout, routeData) {

    $scope.layout = layout;
    $scope.checkRole = authz(current, null);
    $scope.program = routeData.program;

    $scope.search = {
        term: "",
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
}])


;
