'use strict';

angular.module('upmark.submission.submission', [
    'ngResource', 'ui.select', 'upmark.admin.settings', 'upmark.user'])


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
             layout, $location, Current, format, $filter, Notifications,
             Structure, LocationSearch, download) {

    $scope.layout = layout;
    $scope.program = routeData.program;
    $scope.edit = Editor('submission', $scope, {});
    if (routeData.submission) {
        // Editing old
        $scope.submission = routeData.submission;
        $scope.children = routeData.qnodes;
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
            '/2/submission/{}', model.id, $scope.program.id));
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url(format(
            '/2/program/{}', $scope.program.id));
    });

    $scope.checkRole = Authz({
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


.controller('SubmissionDuplicateCtrl', [
        '$scope', 'Submission', 'routeData', 'layout', '$location',
        'Current', 'format', '$filter', 'Notifications',
        function($scope, Submission, routeData, layout, $location,
                 Current, format, $filter, Notifications) {

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
}])


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
        formData.append('program', $scope.program.id);
        formData.append('organisation', $scope.submission.organisation.id);
        formData.append('survey', $scope.submission.survey.id);
        formData.append('title', $scope.submission.title);
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
            $location.url('/2/program/' + response);
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
