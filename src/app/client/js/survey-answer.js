'use strict';

angular.module('wsaa.surveyAnswers', ['ngResource', 'wsaa.admin'])


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


.controller('SubmissionCtrl', [
        '$scope', 'Submission', 'Survey', 'routeData', 'Editor',
        'questionAuthz', 'layout', '$location', 'Current', 'format', '$filter',
        'Notifications', 'Structure', '$http',
        function($scope, Submission, Survey, routeData, Editor, authz,
                 layout, $location, current, format, $filter, Notifications,
                 Structure, $http) {

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
        $scope.edit.params.orgId = routeData.organisation.id;
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

    $scope.setState = function(state) {
        $scope.submission.$save({approval: state},
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
            '/submission/{}', model.id, $scope.program.id));
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url(format(
            '/program/{}', $scope.program.id));
    });

    $scope.checkRole = authz(current, $scope.program, $scope.submission);

    $scope.download = function(export_type) {
        var url = '/export/submission/' + $scope.submission.id;
        url += '/' + export_type + '.xlsx';

        $http.get(url, { responseType: "arraybuffer", cache: false }).then(
            function success(response) {
                var message = "Export finished";
                Notifications.set('export', 'info', message, 5000);
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


.controller('SubmissionImportCtrl', [
        '$scope', 'Submission', 'Survey', 'routeData', 'Editor',
        'questionAuthz', 'layout', '$location', 'Current', 'format', '$filter',
        'Notifications', '$http', '$cookies', '$timeout',
        function($scope, Submission, Survey, routeData, Editor, authz,
                 layout, $location, current, format, $filter, Notifications,
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
            $location.url('/program/' + response);
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

    $scope.checkRole = authz(current, $scope.submission);
}])


;
