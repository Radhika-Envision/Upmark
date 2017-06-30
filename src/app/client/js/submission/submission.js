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


.controller('SubmissionExportCtrl', function(
        $scope, $location, Notifications, LocationSearch, Enqueue) {

    $scope.startCalender = {
      opened: false
    };
    $scope.endCalender = {
      opened: false
    };
    $scope.dateOptions = {
      format: 'MMM yyyy',
      altInputFormats: ['mediumDate', 'dd MMM yyyy', 'MMM yyyy', 'yyyy', 'yyyy-MM-dd'],
      formatYear: 'yyyy',
      startingDay: 1,
    };

    $scope.openStartCalender = function() {
        $scope.startCalender.opened = true;
    };
    $scope.openEndCalender = function() {
        $scope.endCalender.opened = true;
    };

    // Report type
    $scope.$watch('reportSpec.type', function(type) {
        if (!$scope.reportForm || !$scope.reportSpec) {
            return;
        }

        if (type == 'summary') {
            $scope.reportSpec.organisationId = $scope.submission.organisation.id;
        } else {
            $scope.reportSpec.organisationId = null;
        };
    });

    // Date range and interval settings
    $scope.$watch('reportForm.min_date', function(min) {
        if (!$scope.reportForm || !$scope.reportSpec) {
            return;
        };

        $scope.reportSpec.minDate = min.getTime() / 1000;
    });
    $scope.$watch('reportForm.max_date', function(max) {
        if (!$scope.reportForm || !$scope.reportSpec) {
            return;
        };

        $scope.reportSpec.maxDate = max.getTime() / 1000;
    });
    $scope.$watch('reportForm.intervalNum', function(num) {
        if (!$scope.reportForm || !$scope.reportSpec) {
            return;
        }

        // Interval length must be a positive integer
        if (num <= 0.0) {
            $scope.reportForm.intervalNum = null;
        };
        if (num % 1 != 0.0) {
            $scope.reportForm.intervalNum = Math.floor(num)
        };

        // Write to reportSpec
        if ($scope.reportForm.intervalNum != null) {
            $scope.reportSpec.intervalNum = $scope.reportForm.intervalNum;
        } else {
            $scope.reportSpec.intervalNum = 1.0;
        };
    });
    $scope.$watch('reportSpec.intervalUnit', function(unit) {
        if (unit.id == 'months')
            $scope.dateOptions.format = 'MMM yyyy';
        else
            $scope.dateOptions.format = 'yyyy';
    });

    // Location filter settings
    $scope.searchLoc = function(term) {
        return LocationSearch.query({term: term}).$promise;
    };
    $scope.deleteLocation = function(i) {
        $scope.reportForm.locations.splice(i, 1);
    };
    $scope.$watch('reportForm.locations', function(loc) {
        if (!$scope.reportForm || !$scope.reportSpec) {
          return;
        }

        $scope.reportSpec.locations = loc
    })

    // Organisation size filter settings
    $scope.$watch('reportSpec.minInternalFtes', function(ftes) {
        if (!$scope.reportSpec) {
            return
        };
        if (ftes <= 0) {
            $scope.reportSpec.minInternalFtes = null;
            return
        };
        if (ftes != null) {
            $scope.reportSpec.filterSize = true;
        };
    });
    $scope.$watch('reportSpec.maxInternalFtes', function(ftes) {
        if (!$scope.reportSpec) {
            return
        };
        if (ftes <= 0) {
            $scope.reportSpec.maxInternalFtes = null;
            return
        };
        if (ftes != null) {
            $scope.reportSpec.filterSize = true;
        };

    });
    $scope.$watch('reportSpec.minContractors', function(contractors) {
        if (!$scope.reportSpec) {
            return
        };
        if (contractors <= 0) {
            $scope.reportSpec.minContractors = null;
        };
        if (contractors != null) {
            $scope.reportSpec.filterSize = true;
        };
    });
    $scope.$watch('reportSpec.maxExternalFtes', function(contractors) {
        if (!$scope.reportSpec) {
            return
        };
        if (contractors <= 0) {
            $scope.reportSpec.maxExternalFtes = null;
        };
        if (contractors != null) {
            $scope.reportSpec.filterSize = true;
        };
    });
    $scope.$watch('reportSpec.minEmployees', function(employees) {
        if (!$scope.reportSpec) {
            return
        };
        if (employees <= 0) {
            $scope.reportSpec.minEmployees = null;
        };
        if (employees != null) {
            $scope.reportSpec.filterSize = true;
        };
    });
    $scope.$watch('reportSpec.maxEmployees', function(employees) {
        if (!$scope.reportSpec) {
            return
        };
        if (employees <= 0) {
            $scope.reportSpec.maxEmployees = null;
        };
        if (employees != null) {
            $scope.reportSpec.filterSize = true;
        };

    });
    $scope.$watch('reportSpec.minPopulation', function(population) {
        if (!$scope.reportSpec) {
            return
        };
        if (population <= 0) {
            $scope.reportSpec.minPopulation = null;
        };
        if (population != null) {
            $scope.reportSpec.filterSize = true;
        };
    });
    $scope.$watch('reportSpec.maxPopulation', function(population) {
        if (!$scope.reportSpec) {
            return
        };
        if (population <= 0) {
            $scope.reportSpec.maxPopulation = null;
        };
        if (population != null) {
            $scope.reportSpec.filterSize = true;
        };
    });

    // Approval status filter
    $scope.setReportApproval = function(state) {
        $scope.reportSpec.approval = state;
    }

    // Report form
    $scope.openReportForm = function() {
        if (!$scope.reportForm) {
            var dt = new Date();
            dt.setFullYear(dt.getFullYear() - 1);
            $scope.reportForm = {
                intervalUnits: [
                    {name: 'Months', id: 'months'},
                    {name: 'Years', id: 'years'}],
                intervalNum: 1.0,
                allowedStates: ['reviewed', 'approved'],
                locations: [],
                min_date: dt,
                max_date: new Date()
            }

            if ($scope.checkRole('report_temporal_full'))
                $scope.reportForm.allowedStates = null;

        } else {
                $scope.reportForm.open = true;
        };

        if (!$scope.reportSpec) {
            // Initial report spec
            $scope.reportSpec = {
                type: 'summary',
                minDate: null,
                maxDate: null,
                intervalNum: null,
                intervalUnit: $scope.reportForm.intervalUnits[0],
                filterSize: false,
                minConstituents: 5,
                minInternalFtes: null,
                maxInternalFtes: null,
                minContractors: null,
                maxExternalFtes: null,
                minEmployees: null,
                maxEmployees: null,
                minPopulation: null,
                maxPopulation: null,
                quality: 0,
                approval: 'reviewed',
                locations: null,
                organisationId: null
            };
        };
    };

    $scope.closeReportForm = function() {
        $scope.reports.formOpen = false;
        $scope.reportForm = null;
        $scope.reportSpec = null;
        $scope.startCalender.opened = false;
        $scope.endCalender.opened = false;
    }

    // Report form exporter
    $scope.specTest = function(spec) {
        // Test start and end dates are sensible
        if (spec.minDate >= spec.maxDate) {
            alert("Invalid input: start date equal to or later than end date");
            return false;
        }

        // Test min/max pairs are sensible if set
        return true;
    };

    $scope.downloadTemporalReport = Enqueue(function(query, file_type, survey_id) {
        if (!$scope.specTest(query))
            return;
        var fileName = 'submission-temporal.' + file_type;
        var url = '/report/sub/temporal/' + survey_id + '.' + file_type;
        query = angular.copy(query);
        query.intervalUnit = query.intervalUnit.id;
        $scope.download(fileName, url, query);
    }, 500, $scope);

    $scope.openReportForm();
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


.directive('submissionSelect', [function() {
    return {
        restrict: 'AEC',
        templateUrl: 'submission_select.html',
        scope: {
            submission: '=submissionSelect',
            org: '=',
            program: '=',
            track: '@',
            survey: '=',
            formatUrl: '=',
            disallowNone: '='
        },
        controller: ['$scope', 'Current', 'Submission', 'Organisation',
                '$location', 'format', 'Notifications', 'PurchasedSurvey',
                'Structure', 'Authz', 'Enqueue',
                function($scope, current, Submission, Organisation,
                         $location, format, Notifications, PurchasedSurvey,
                         Structure, Authz, Enqueue) {

            $scope.aSearch = {
                organisation: null,
                historical: false
            };

            $scope.$watch('submission.organisation', function(org) {
                if (!org)
                    org = $scope.org || current.user.organisation;
                $scope.aSearch.organisation = org;
            });

            $scope.searchOrg = function(term) {
                return Organisation.query({term: term}).$promise;
            };
            $scope.$watch('aSearch.organisation', function(organisation) {
                if (organisation)
                    $scope.search.organisationId = organisation.id;
                else
                    $scope.search.organisationId = null;
            });

            $scope.$watch('survey', function(survey) {
                $scope.search.surveyId = survey ? survey.id : null;
            });

            $scope.$watchGroup(['program', 'aSearch.historical'], function(vars) {
                var program = vars[0],
                    historical = vars[1];

                if (historical) {
                    $scope.search.trackingId = program ? program.trackingId : null;
                    $scope.search.programId = null;
                } else {
                    $scope.search.trackingId = null;
                    $scope.search.programId = program ? program.id : null;
                }
            });
            $scope.$watch('track', function(track) {
                $scope.aSearch.historical = track != null;
                $scope.showEdit = track == null;
            });

            $scope.historical = false;
            $scope.search = {
                term: "",
                organisationId: null,
                surveyId: null,
                programId: null,
                trackingId: null,
                deleted: false,
                page: 0,
                pageSize: 5
            };
            $scope.applySearch = Enqueue(function() {
                Submission.query($scope.search).$promise.then(
                    function success(submissions) {
                        $scope.submissions = submissions;
                    },
                    function failure(details) {
                        Notifications.set('program', 'error',
                            "Could not get submission list: " + details.statusText);
                    }
                );
            }, 100, $scope);
            $scope.$watch('search', $scope.applySearch, true);

            $scope.$watchGroup(['program', 'search.organisationId', 'survey', 'track'],
                    function(vars) {

                var program = vars[0];
                var organisationId = vars[1];
                var survey = vars[2];
                var track = vars[3];

                if (!program || !organisationId || !survey || track != null) {
                    $scope.purchasedSurvey = null;
                    return;
                }

                PurchasedSurvey.head({
                    programId: program.id,
                    id: organisationId,
                    hid: survey.id
                }, null, function success(purchasedSurvey) {
                    $scope.purchasedSurvey = purchasedSurvey;
                }, function failure(details) {
                    if (details.status == 404) {
                        $scope.purchasedSurvey = null;
                        return;
                    }
                    Notifications.set('program', 'error',
                        "Could not get purchase status: " + details.statusText);
                });
            });

            // Allow parent controller to specify a special URL formatter - this
            // is so one can switch between submissions without losing one's
            // place in the survey.
            $scope.getSubmissionUrl = function(submission) {
                if ($scope.formatUrl)
                    return $scope.formatUrl(submission)

                if (submission) {
                    return format('/2/submission/{}', submission.id);
                } else {
                    return format('/2/survey/{}?program={}',
                        $scope.survey.id, $scope.program.id);
                }
            };

            $scope.checkRole = Authz({
                program: $scope.program,
                org: $scope.org,
            });
        }]
    }
}])
