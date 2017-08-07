'use strict';

angular.module('upmark.submission.select', ['ui.select', 'upmark.user'])


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
        controller: function(
                $scope, currentUser, Submission, Organisation,
                $location, format, Notifications, PurchasedSurvey,
                Structure, Authz, Enqueue) {

            $scope.aSearch = {
                organisation: null,
                historical: false
            };

            $scope.$watch('submission.organisation', function(org) {
                if (!org)
                    org = $scope.org || currentUser.organisation;
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

            $scope.$watchGroup(['aSearch.organisation', 'program'], function(vals) {
                var org = vals[0];
                var program = vals[1];
                $scope.checkRole = Authz({
                    program: program,
                    org: org,
                });
            });
        }
    }
}])
