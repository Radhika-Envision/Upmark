'use strict';

angular.module('upmark.submission.submission', [
    'ngResource', 'ui.select', 'upmark.admin.settings', 'upmark.user',
    'upmark.chain'])


.config(function($routeProvider, chainProvider) {
    $routeProvider
        .when('/:uv/submission/new', {
            templateUrl : 'submission.html',
            controller : 'SubmissionCtrl',
            resolve: {routeData: chainProvider({
                program: ['Program', '$route', function(Program, $route) {
                    return Program.get({
                        id: $route.current.params.program
                    }).$promise;
                }],
                organisation: ['Organisation', '$route',
                        function(Organisation, $route) {
                    if (!$route.current.params.organisation)
                        return null;
                    return Organisation.get({
                        id: $route.current.params.organisation
                    }).$promise;
                }],
                surveys: ['Survey', 'program',
                        function(Survey, program) {
                    return Survey.query({
                        programId: program.id,
                        deleted: false,
                    }).$promise;
                }],
                duplicate: ['Submission', '$route',
                        function(Submission, $route) {
                    if (!$route.current.params.duplicate)
                        return null;
                    return Submission.get({
                        id: $route.current.params.duplicate
                    }).$promise;
                }]
            })}
        })
        .when('/:uv/submission/duplicate', {
            templateUrl : 'submission_dup.html',
            controller : 'SubmissionDuplicateCtrl',
            resolve: {routeData: chainProvider({
                program: ['Program', '$route', function(Program, $route) {
                    return Program.get({
                        id: $route.current.params.program
                    }).$promise;
                }],
                organisation: ['Organisation', '$route',
                        function(Organisation, $route) {
                    if (!$route.current.params.organisation)
                        return null;
                    return Organisation.get({
                        id: $route.current.params.organisation
                    }).$promise;
                }]
            })}
        })
        .when('/:uv/submission/import', {
            templateUrl : 'submission_import.html',
            controller : 'SubmissionImportCtrl',
            resolve: {routeData: chainProvider({
                program: ['Program', '$route', function(Program, $route) {
                    return Program.get({
                        id: $route.current.params.program
                    }).$promise;
                }],
                organisation: ['Organisation', '$route',
                        function(Organisation, $route) {
                    if (!$route.current.params.organisation)
                        return null;
                    return Organisation.get({
                        id: $route.current.params.organisation
                    }).$promise;
                }],
                surveys: ['Survey', 'program',
                        function(Survey, program) {
                    return Survey.query({
                        programId: program.id
                    }).$promise;
                }]
            })}
        })
        .when('/:uv/submission/:submission', {
            templateUrl : 'submission.html',
            controller : 'SubmissionCtrl',
            resolve: {routeData: chainProvider({
                submission: ['Submission', '$route',
                        function(Submission, $route) {
                    return Submission.get({
                        id: $route.current.params.submission
                    }).$promise;
                }],
                program: ['submission', function(submission) {
                    return submission.program;
                }]
            })}
        })
    ;
})


.factory('Submission', ['$resource', 'paged', function($resource, paged) {
    return $resource('/submission/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        create: { method: 'POST' },
        save: { method: 'PUT' },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        }
    });
}])


.controller('SubmissionCtrl',
        function($scope, Submission, Survey, routeData, Editor, Authz,
             layout, $location, format, $filter, Notifications,
             Structure, LocationSearch, download) {
    // hard copy survey id in production to keep export menu for old survey
    // for new survey only need one export menu 'One measure per row'  
    // **** last item "5f6b69cf-6338-4cd2-8fb8-3e6456c0ff6a" fro testing stage, remove when deploy to production
    let oldSurvey = ["19c574ad-4a02-4980-9f4a-6928ef4bc4f1",
                     "d4688eae-a732-47a2-8389-23ecdf495f04",
                     "c4ad63f1-2f10-465f-b3e6-74944602c624",
                     "eeb94743-ae00-412d-b89a-639b03677bc5",
                     "bda5e693-cd1f-4b3d-ab1b-8519f019272b",
                     "d4688eae-a732-47a2-8389-23ecdf495f04",
                     "18eab68c-1936-41e6-9de7-88d4d53a487e",
                     "eeb94743-ae00-412d-b89a-639b03677bc5",
                     "d4688eae-a732-47a2-8389-23ecdf495f04",
                     "067248b9-ee0d-4507-aad7-31159f636502",
                     "44ef39ac-b8bb-4412-b522-27b82e90a836",
                     "c8ed0f05-1a4f-49d5-b965-f3b25c74765a",
                     "19c574ad-4a02-4980-9f4a-6928ef4bc4f1",
                     "c4ad63f1-2f10-465f-b3e6-74944602c624",
                     "14a90222-7783-48c7-8127-ad10d00007c3",
                     "8ebb3782-49f7-447c-b7dc-d3c8417f12fa",
                     "4159bcbf-4416-4f94-b07a-c02c7fa4bf6a",
                     "284a5043-ffe5-4920-bb66-6a9adfa09973",
                     "57108d7a-f69e-4120-8d16-ac22f383eb0f",
                     "af7021fc-0de0-4410-975e-06ee604e225d",
                     "9ddabc3c-d259-433e-80f9-621fd685225b",
                     "7b490e0f-3e04-40e6-97ad-2ab52d19e526",
                     "d68d14cb-ad72-478c-af70-a37948e36838",
                     "5f6b69cf-6338-4cd2-8fb8-3e6456c0ff6a"];
    $scope.layout = layout;
    $scope.program = routeData.program;
    $scope.edit = Editor('submission', $scope, {});
    if (routeData.submission) {
        // Editing old
        $scope.submission = routeData.submission;
        $scope.children = routeData.qnodes;
        if (oldSurvey.indexOf($scope.submission.survey.id) < 0)
            $scope.hideExportMenu=true;
    } else {
        // Creating new
        $scope.submission = new Submission({
            program: $scope.program,
            organisation: routeData.organisation
        });
        $scope.edit.params.programId = $scope.program.id;
        $scope.edit.params.organisationId = routeData.organisation.id;
        $scope.surveys = routeData.surveys;
        if ($scope.surveys.length == 1) {
            $scope.submission.survey = $scope.surveys[0];
            // Patch in program, which is needed by Structure by is not provided
            // by the web service when requesting a list.
            $scope.submission.survey.program = $scope.program;
        }
        $scope.duplicate = routeData.duplicate;
        if ($scope.duplicate)
            $scope.edit.params.duplicateId = $scope.duplicate.id;
        $scope.edit.edit();
    }

    $scope.format = "dd/MM/yyyy";
    $scope.$watch('edit.model.created', function (created) {
        if (!$scope.edit.model)
            return;
        $scope.edit.model.$created = new Date(1000 * created);
    });
    $scope.$watch('edit.model.$created', function (created) {
        if (!$scope.edit.model)
            return;
        if (created != null) {
            $scope.edit.model.created = created.getTime() / 1000;
            $scope.date = created;
        };
    });
    $scope.date = new Date(1000 * $scope.submission.created);
    $scope.reports = {
        formOpen: false,
    };

    $scope.$watchGroup(['submission', 'submission.deleted'], function(vars) {
        var submission = vars[0];
        if (!submission)
            return;
        $scope.structure = Structure(submission);
    });

    $scope.$watch('edit.model.survey', function(survey) {
        // Generate title first time
        if (!survey || !$scope.edit.model)
            return;
        if (!$scope.edit.model.title) {
            $scope.edit.model.title = format('{} - {}',
                survey.title, $filter('date')(new Date(), 'MMM yyyy'));
        }
        $scope.edit.params.surveyId = survey.id;
    });

    $scope.setState = function(state, $event) {
        $scope.submission.$save({approval: state},
            function success() {
                $scope.$broadcast("state-changed");
                Notifications.set('edit', 'success', "Saved", 5000);
            },
            function failure(details) {
                Notifications.set('edit', 'error',
                    "Could not save: " + details.statusText);
            }
        );
        // Stop the approval buttons from updating: that will happen
        // asynchronously, when the submission has finished saving. The result
        // might be different than what is requested.
        $event.preventDefault();
    };

    $scope.$on('EditSaved', function(event, model) {
        $location.url(format(
            '/3/submission/{}', model.id, $scope.program.id));
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url(format(
            '/3/program/{}', $scope.program.id));
    });

    $scope.checkRole = Authz({
        org: $scope.submission.organisation,
        program: $scope.program,
        submission: $scope.submission,
    });

    $scope.download = function(namePattern, url, data) {
        $scope.headerMessage = "Generating report"
        var success = function success(response) {
            var message = "Export finished.";
            if (response.headers('Operation-Details'))
                message += ' ' + response.headers('Operation-Details');
            Notifications.set('export', 'info', message, 5000);
            $scope.headerMessage = null;
        };
        var failure = function failure(response) {
            Notifications.set('export', 'error',
                "Error: " + response.statusText);
            $scope.headerMessage = null;
        };
        return download(namePattern, url, data).then(success, failure);
    };

    $scope.downloadSubmissionReport = function(report_type, submission_id) {
        var fileName = 'submission-' + report_type + '.xlsx';
        var url = '/report/sub/export/' + submission_id;
        url += '/' + report_type + '.xlsx';
        $scope.download(fileName, url, null);
    };

    $scope.calender = {
      opened: false
    };

    $scope.dateOptions = {
      format: 'mediumDate',
      formatYear: 'yyyy',
      startingDay: 1,
    };

    $scope.openCalender = function() {
        $scope.calender.opened = true
    };
})


.controller('SubmissionDuplicateCtrl', function(
        $scope, Submission, routeData, layout, $location,
        format, $filter, Notifications) {

    $scope.layout = layout;
    $scope.program = routeData.program;
    $scope.organisation = routeData.organisation;
    $scope.submissions = null;

    $scope.search = {
        term: "",
        trackingId: $scope.program.trackingId,
        organisationId: $scope.organisation.id,
        approval: 'draft',
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        Submission.query(search).$promise.then(function(submissions) {
            $scope.submissions = submissions;
        });
    }, true);
    $scope.cycleApproval = function() {
        var states = ['draft', 'final', 'reviewed', 'approved'];
        var i = states.indexOf($scope.search.approval);
        if (i >= states.length - 1)
            i = -1;
        $scope.search.approval = states[i + 1];
    };
})


.controller('SubmissionImportCtrl', function(
        $scope, Submission, Survey, routeData, Editor, Authz,
        layout, $location, format, $filter, Notifications,
        $http, $cookies, $timeout) {

    $scope.program = routeData.program;
    $scope.surveys = routeData.surveys;
    $scope.progress = {
        isWorking: false,
        isFinished: false,
        uploadFraction: 0.0
    };
    Notifications.remove('import');
    $scope.submission = new Submission({
        program: $scope.program,
        survey : null,
        title: "Imported Submission",
        organisation: routeData.organisation
    });
    if ($scope.surveys.length == 1) {
        $scope.submission.survey = $scope.surveys[0];
    }

    var headers = {};
    var xsrfName = $http.defaults.xsrfHeaderName;
    headers[xsrfName] = $cookies.get($http.defaults.xsrfCookieName);

    var config = {
        url: '/import/submission.json',
        maxFilesize: 50,
        paramName: "file",
        acceptedFiles: ".xls,.xlsx",
        headers: headers,
        autoProcessQueue: false
    };

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
        formData.append('submission', angular.toJson($scope.submission));
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
            $location.url('/3/submission/' + response);
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

    $scope.checkRole = Authz({submission: $scope.submission});
})

;
