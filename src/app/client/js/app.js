'use strict';

angular.module('upmark', [
    'angular-input-stars',
    'angular-medium-editor',
    'angular-select-text',
    'cfp.hotkeys',
    'diff-match-patch',
    'msieurtoph.ngCheckboxes',
    'ngAnimate',
    'ngRoute',
    'ui.bootstrap',
    'ui.bootstrap.showErrors',
    'upmark.admin.settings',
    'upmark.authz',
    'upmark.cache_bust',
    'upmark.chain',
    'upmark.current_user',
    'upmark.custom',
    'upmark.diff',
    'upmark.group',
    'upmark.home',
    'upmark.location',
    'upmark.notifications',
    'upmark.organisation',
    'upmark.response.type',
    'upmark.root',
    'upmark.route_version',
    'upmark.settings',
    'upmark.statistics',
    'upmark.subscription',
    'upmark.submission.approval',
    'upmark.submission.export',
    'upmark.submission.header',
    'upmark.submission.response',
    'upmark.submission.rnode',
    'upmark.submission.select',
    'upmark.submission.submission',
    'upmark.survey',
    'upmark.survey.history',
    'upmark.survey.layout',
    'upmark.survey.measure',
    'upmark.survey.program',
    'upmark.survey.qnode',
    'upmark.structure',
    'upmark.survey.survey',
    'upmark.system',
    'upmark.user',
    'validation.match',
    'vpac.utils.arrays',
    'vpac.utils.events',
    'vpac.utils.logging',
    'vpac.utils.math',
    'vpac.utils.observer',
    'vpac.utils.queue',
    'vpac.utils.requests',
    'vpac.utils.session',
    'vpac.utils.string',
    'vpac.utils.cycle',
    'vpac.utils.watch',
    'vpac.widgets.any-href',
    'vpac.widgets.dimmer',
    'vpac.widgets.docs',
    'vpac.widgets.editor',
    'vpac.widgets.form-controls',
    'vpac.widgets.markdown',
    'vpac.widgets.page-title',
    'vpac.widgets.progress',
    'vpac.widgets.size',
    'vpac.widgets.spinner',
    'vpac.widgets.text',
    'vpac.widgets.time',
    'vpac.widgets.visibility',
    'yaru22.angular-timeago',
])


.config(['$routeProvider', '$httpProvider', '$parseProvider', '$animateProvider',
         'logProvider', 'chainProvider', '$locationProvider',
        function($routeProvider, $httpProvider, $parseProvider, $animateProvider,
                logProvider, chain, $locationProvider) {

        // Revert behaviour: URLs do not need to have a `!` prefix.
        // https://github.com/angular/angular.js/commit/aa077e81129c740041438688dff2e8d20c3d7b52
        // https://webmasters.googleblog.com/2015/10/deprecating-our-ajax-crawling-scheme.html
        $locationProvider.hashPrefix('');

        $routeProvider

            .when('/:uv/', {
                templateUrl : 'home.html',
                controller : 'HomeCtrl'
            })

            .when('/:uv/admin', {
                templateUrl : 'systemconfig.html',
                controller : 'SystemConfigCtrl',
                resolve: {
                    systemConfig: ['SystemConfig', function(SystemConfig) {
                        return SystemConfig.get().$promise;
                    }]
                }
            })

            .when('/:uv/subscription/:type', {
                templateUrl : 'subscription.html',
                controller : 'SubscriptionCtrl'
            })

            .when('/:uv/groups', {
                templateUrl : 'group_list.html',
                controller : 'GroupListCtrl'
            })
            .when('/:uv/group/new', {
                templateUrl : 'group.html',
                controller : 'GroupCtrl',
                resolve: {
                    group: function() {
                        return null;
                    }
                }
            })
            .when('/:uv/group/:id', {
                templateUrl : 'group.html',
                controller : 'GroupCtrl',
                resolve: {
                    group: ['Group', '$route',
                            function(Group, $route) {
                        return Group.get({
                            id: $route.current.params.id
                        }).$promise;
                    }]
                }
            })

            .when('/:uv/users', {
                templateUrl : 'user_list.html',
                controller : 'UserListCtrl'
            })
            .when('/:uv/user/new', {
                templateUrl : 'user.html',
                controller : 'UserCtrl',
                resolve: {routeData: chain({})},
            })
            .when('/:uv/user/:id', {
                templateUrl : 'user.html',
                controller : 'UserCtrl',
                resolve: {routeData: chain({
                    user: ['User', '$route', function(User, $route) {
                        return User.get($route.current.params).$promise;
                    }]
                })}
            })

            .when('/:uv/orgs', {
                templateUrl : 'organisation_list.html',
                controller : 'OrganisationListCtrl'
            })
            .when('/:uv/org/new', {
                templateUrl : 'organisation.html',
                controller : 'OrganisationCtrl',
                resolve: {
                    org: function() {
                        return null;
                    }
                }
            })
            .when('/:uv/org/:id', {
                templateUrl : 'organisation.html',
                controller : 'OrganisationCtrl',
                resolve: {
                    org: ['Organisation', '$route',
                            function(Organisation, $route) {
                        return Organisation.get({
                            id: $route.current.params.id
                        }).$promise;
                    }]
                }
            })
            .when('/:uv/org/:id/survey/add', {
                templateUrl : 'purchased_survey.html',
                controller : 'PurchasedSurveyAddCtrl',
                resolve: {
                    org: ['Organisation', '$route',
                            function(Organisation, $route) {
                        return Organisation.get($route.current.params).$promise;
                    }],
                    program: ['Program', '$route',
                            function(Program, $route) {
                        if (!$route.current.params.program)
                            return null;
                        return Program.get({
                            id: $route.current.params.program
                        }).$promise;
                    }],
                    surveys: ['Survey', '$route',
                            function(Survey, $route) {
                        if (!$route.current.params.program)
                            return null;
                        return Survey.query({
                            programId: $route.current.params.program
                        }).$promise;
                    }]
                }
            })

            .when('/:uv/programs', {
                templateUrl : 'program_list.html',
                controller : 'ProgramListCtrl'
            })
            .when('/:uv/program/new', {
                templateUrl : 'program.html',
                controller : 'ProgramCtrl',
                resolve: {routeData: chain({
                    duplicate: ['Program', '$route', function(Program, $route) {
                        if (!$route.current.params.duplicate)
                            return null;
                        return Program.get({
                            id: $route.current.params.duplicate
                        }).$promise;
                    }]
                })}
            })
            .when('/:uv/program/import', {
                templateUrl : 'program_import.html',
                controller : 'ProgramImportCtrl'
            })
            .when('/:uv/program/:program', {
                templateUrl : 'program.html',
                controller : 'ProgramCtrl',
                resolve: {routeData: chain({
                    program: ['Program', '$route', function(Program, $route) {
                        return Program.get({
                            id: $route.current.params.program
                        }).$promise;
                    }]
                })}
            })

            .when('/:uv/survey/new', {
                templateUrl : 'survey.html',
                controller : 'SurveyCtrl',
                resolve: {routeData: chain({
                    program: ['Program', '$route', function(Program, $route) {
                        return Program.get({
                            id: $route.current.params.program
                        }).$promise;
                    }]
                })}
            })
            .when('/:uv/survey/:survey/choice', {
                templateUrl : 'survey_choice.html',
                controller : 'SurveyChoiceCtrl',
                resolve: {routeData: chain({
                    survey: ['Survey', '$route',
                            function(Survey, $route) {
                        return Survey.get({
                            id: $route.current.params.survey,
                            programId: $route.current.params.program
                        }).$promise;
                    }],
                    program: ['survey', function(survey) {
                        return survey.program;
                    }],
                    org: ['Organisation', '$route',
                            function(Organisation, $route) {
                        if (!$route.current.params.organisation)
                            return null;
                        return Organisation.get({
                            id: $route.current.params.organisation
                        }).$promise;
                    }]
                })}
            })
            .when('/:uv/survey/:survey', {
                templateUrl : 'survey.html',
                controller : 'SurveyCtrl',
                resolve: {routeData: chain({
                    survey: ['Survey', '$route',
                            function(Survey, $route) {
                        return Survey.get({
                            id: $route.current.params.survey,
                            programId: $route.current.params.program
                        }).$promise;
                    }],
                    program: ['survey', function(survey) {
                        return survey.program;
                    }]
                })}
            })

            .when('/:uv/submission/new', {
                templateUrl : 'submission.html',
                controller : 'SubmissionCtrl',
                resolve: {routeData: chain({
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
                resolve: {routeData: chain({
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
                resolve: {routeData: chain({
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
                resolve: {routeData: chain({
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

            .when('/:uv/qnode/new', {
                templateUrl : 'qnode.html',
                controller : 'QuestionNodeCtrl',
                resolve: {routeData: chain({
                    survey: ['Survey', '$route',
                            function(Survey, $route) {
                        var surveyId = $route.current.params.survey;
                        if (!surveyId)
                            return null
                        return Survey.get({
                            id: surveyId,
                            programId: $route.current.params.program
                        }).$promise;
                    }],
                    parent: ['QuestionNode', '$route',
                            function(QuestionNode, $route) {
                        var parentId = $route.current.params.parent;
                        if (!parentId)
                            return null;
                        return QuestionNode.get({
                            id: parentId,
                            programId: $route.current.params.program
                        }).$promise;
                    }]
                })}
            })
            .when('/:uv/qnode/:qnode', {
                templateUrl : 'qnode.html',
                controller : 'QuestionNodeCtrl',
                resolve: {routeData: chain({
                    submission: ['Submission', '$route',
                            function(Submission, $route) {
                        if (!$route.current.params.submission)
                            return null;
                        return Submission.get({
                            id: $route.current.params.submission
                        }).$promise;
                    }],
                    qnode: ['QuestionNode', '$route', 'submission',
                            function(QuestionNode, $route, submission) {
                        return QuestionNode.get({
                            id: $route.current.params.qnode,
                            programId: submission ? submission.program.id :
                                $route.current.params.program,
                        }).$promise;
                    }],
                    measures: ['Measure', '$route', 'submission',
                            function(Measure, $route, submission) {
                        return Measure.query({
                            qnodeId: $route.current.params.qnode,
                            programId: submission ? submission.program.id :
                                $route.current.params.program,
                        }).$promise;
                    }]
                })}
            })
            .when('/:uv/qnode-link', {
                templateUrl : 'qnode_link.html',
                controller : 'QnodeLinkCtrl',
                resolve: {routeData: chain({
                    survey: ['Survey', '$route',
                            function(Survey, $route) {
                        if (!$route.current.params.survey)
                            return null;
                        return Survey.get({
                            id: $route.current.params.survey,
                            programId: $route.current.params.program
                        }).$promise;
                    }],
                    parent: ['QuestionNode', '$route',
                            function(QuestionNode, $route) {
                        if (!$route.current.params.parent)
                            return null;
                        return QuestionNode.get({
                            id: $route.current.params.parent,
                            programId: $route.current.params.program
                        }).$promise;
                    }],
                    program: ['Program', '$route', function(Program, $route) {
                        return Program.get({
                            id: $route.current.params.program
                        }).$promise;
                    }],
                })}
            })
            .when('/:uv/measure-link', {
                templateUrl : 'measure_link.html',
                controller : 'MeasureLinkCtrl',
                resolve: {routeData: chain({
                    parent: ['QuestionNode', '$route',
                            function(QuestionNode, $route) {
                        return QuestionNode.get({
                            id: $route.current.params.parent,
                            programId: $route.current.params.program
                        }).$promise;
                    }],
                    program: ['Program', '$route', function(Program, $route) {
                        return Program.get({
                            id: $route.current.params.program
                        }).$promise;
                    }],
                })}
            })

            .when('/:uv/statistics', {
                templateUrl : 'statistics.html',
                controller : 'StatisticsCtrl',
                resolve: {routeData: chain({
                    submission1: ['Submission', '$route',
                            function(Submission, $route) {
                        return Submission.get({
                            id: $route.current.params.submission1
                        }).$promise;
                    }],
                    submission2: ['Submission', '$route',
                            function(Submission, $route) {
                        if (!$route.current.params.submission2)
                            return null;
                        return Submission.get({
                            id: $route.current.params.submission2
                        }).$promise;
                    }],
                    rnodes1: ['ResponseNode', '$route',
                            function(ResponseNode, $route) {
                        var qnodeId = $route.current.params.qnode;
                        return ResponseNode.query({
                            submissionId: $route.current.params.submission1,
                            parentId: qnodeId,
                            root: qnodeId ? null : ''
                        }).$promise;
                    }],
                    rnodes2: ['ResponseNode', '$route',
                            function(ResponseNode, $route) {
                        if (!$route.current.params.submission2)
                            return null;
                        var qnodeId = $route.current.params.qnode;
                        return ResponseNode.query({
                            submissionId: $route.current.params.submission2,
                            parentId: qnodeId,
                            root: qnodeId ? null : ''
                        }).$promise;
                    }],
                    approvals: ['submission1', 'submission2', '$q',
                            function(submission1, submission2, $q) {
                        var approvalStates = [
                            'draft', 'final', 'reviewed', 'approved'];
                        var minIndex = approvalStates.indexOf(
                            submission1.survey.minStatsApproval);
                        if (minIndex < 0) {
                            return $q.reject(
                                "Statistics have been disabled for this survey");
                        }
                        if (submission2) {
                            var minIndex2 = approvalStates.indexOf(
                                submission2.survey.minStatsApproval);
                            if (minIndex2 < 0) {
                                return $q.reject(
                                    "Statistics have been disabled for this survey");
                            }
                            if (minIndex2 > minIndex)
                                minIndex = minIndex2;
                        }
                        return approvalStates.slice(minIndex);
                    }],
                    approval: ['$route', 'approvals', '$q',
                            function($route, approvals, $q) {
                        var approval = $route.current.params.approval || approvals[0];
                        if (approvals.indexOf(approval) < 0) {
                            return $q.reject(
                                "You can't view data for that approval state");
                        }
                        return approval;
                    }],
                    stats1: ['Statistics', '$route', 'submission1', '$q',
                                'submission2', 'approval',
                            function(Statistics, $route, submission1, $q,
                                submission2, approval) {
                        return Statistics.get({
                            programId: submission1.program.id,
                            surveyId: submission1.survey.id,
                            parentId: $route.current.params.qnode == '' ?
                                null : $route.current.params.qnode,
                            approval: approval
                        }).$promise.then(function(stats1) {
                            if (!submission2 && stats1.length == 0) {
                                return $q.reject(
                                    "There is no data for that category");
                            }
                            else if (stats1.length == 0) {
                                return $q.reject(
                                    "There is no data for that category of" +
                                    " the first survey/submission");
                            }
                            return stats1;
                        });
                    }],
                    stats2: ['Statistics', '$route', 'submission1', '$q',
                                     'submission2', 'approval', 'stats1',
                             function(Statistics, $route, submission1, $q,
                                     submission2, approval, stats1) {
                        if (!submission2)
                            return null;
                        if (submission1.program.id == submission2.program.id)
                            return stats1;
                        return Statistics.get({
                            programId: submission2.program.id,
                            surveyId: submission2.survey.id,
                            parentId: $route.current.params.qnode == '' ?
                                null : $route.current.params.qnode,
                            approval: approval
                        }).$promise.then(function(stats1) {
                            if (stats1.length == 0) {
                                return $q.reject(
                                    "There is no data for that category of" +
                                    " the second survey/submission");
                            }
                            return stats1;
                        });
                    }],
                    qnode1: ['QuestionNode', '$route', 'submission1',
                            function(QuestionNode, $route, submission1) {
                        if (!$route.current.params.qnode)
                            return null;
                        return QuestionNode.get({
                            programId: submission1.program.id,
                            id: $route.current.params.qnode == '' ?
                                null : $route.current.params.qnode
                        }).$promise;
                    }],
                    qnode2: ['QuestionNode', '$route', 'submission1',
                             'submission2', 'qnode1',
                            function(QuestionNode, $route, submission1,
                                     submission2, qnode1) {
                        if (!$route.current.params.qnode)
                            return null;
                        if (!submission2)
                            return null;
                        if (submission1.program.id == submission2.program.id)
                            return qnode1;
                        return QuestionNode.get({
                            programId: submission2.program.id,
                            id: $route.current.params.qnode == '' ?
                                null : $route.current.params.qnode
                        }).$promise;
                    }]
                })}
            })
            .when('/:uv/diff/:program1/:program2/:survey', {
                templateUrl: 'diff.html',
                controller: 'DiffCtrl',
                reloadOnSearch: false,
                resolve: {routeData: chain({
                    survey1: ['Survey', '$route',
                            function(Survey, $route) {
                        return Survey.get({
                            id: $route.current.params.survey,
                            programId: $route.current.params.program1
                        }).$promise;
                    }],
                    survey2: ['Survey', '$route',
                            function(Survey, $route) {
                        return Survey.get({
                            id: $route.current.params.survey,
                            programId: $route.current.params.program2
                        }).$promise;
                    }]
                })}
            })

            .when('/:uv/custom', {
                templateUrl : 'custom_list.html',
                controller : 'CustomListCtrl',
            })
            .when('/:uv/custom/new', {
                templateUrl : 'custom.html',
                controller : 'CustomCtrl',
                resolve: {routeData: chain({
                    config: ['CustomQueryConfig', function(CustomQueryConfig) {
                        return CustomQueryConfig.get({}).$promise;
                    }],
                    duplicate: ['CustomQuery', '$route', function(CustomQuery, $route) {
                        var id = $route.current.params.duplicate;
                        if (!id)
                            return null;
                        return CustomQuery.get({id: id}).$promise;
                    }],
                })}
            })
            .when('/:uv/custom/:id', {
                templateUrl : 'custom.html',
                controller : 'CustomCtrl',
                resolve: {routeData: chain({
                    config: ['CustomQueryConfig', function(CustomQueryConfig) {
                        return CustomQueryConfig.get({}).$promise;
                    }],
                    query: ['CustomQuery', '$route', function(CustomQuery, $route) {
                        var id = $route.current.params.id;
                        if (id == 'new')
                            return null;
                        return CustomQuery.get({id: id}).$promise;
                    }],
                })}
            })

            .when('/:uv/measures', {
                templateUrl : 'measure_list.html',
                controller : 'MeasureListCtrl',
                resolve: {routeData: chain({
                    program: ['Program', '$route', function(Program, $route) {
                        return Program.get({
                            id: $route.current.params.program
                        }).$promise;
                    }],
                })}
            })
            .when('/:uv/measure/new', {
                templateUrl : 'measure.html',
                controller : 'MeasureCtrl',
                resolve: {routeData: chain({
                    parent: ['QuestionNode', '$route',
                            function(QuestionNode, $route) {
                        if (!$route.current.params.parent)
                            return null;
                        return QuestionNode.get({
                            id: $route.current.params.parent,
                            programId: $route.current.params.program
                        }).$promise;
                    }],
                    program: ['Program', '$route', function(Program, $route) {
                        return Program.get({
                            id: $route.current.params.program
                        }).$promise;
                    }],
                })}
            })
            .when('/:uv/measure/:measure', {
                templateUrl : 'measure.html',
                controller : 'MeasureCtrl',
                resolve: {routeData: chain({
                    submission: ['Submission', '$route',
                            function(Submission, $route) {
                        if (!$route.current.params.submission)
                            return null;
                        return Submission.get({
                            id: $route.current.params.submission
                        }).$promise;
                    }],
                    measure: ['Measure', '$route', 'submission',
                            function(Measure, $route, submission) {
                        return Measure.get({
                            id: $route.current.params.measure,
                            programId: submission ? submission.program.id :
                                $route.current.params.program,
                            surveyId: submission ? submission.survey.id :
                                $route.current.params.survey,
                            submissionId: $route.current.params.submission
                        }).$promise;
                    }],
                    responseType: ['measure', 'ResponseType',
                            function(measure, ResponseType) {
                        return ResponseType.get({
                            id: measure.responseTypeId,
                            programId: measure.programId
                        }).$promise;
                    }]
                })}
            })
            .when('/:uv/response-type/:responseType', {
                templateUrl : 'response_type.html',
                controller : 'ResponseTypeCtrl',
                resolve: {routeData: chain({
                    responseType: ['ResponseType', '$route',
                            function(ResponseType, $route) {
                        return ResponseType.get({
                            id: $route.current.params.responseType,
                            programId: $route.current.params.program
                        }).$promise;
                    }]
                })}
            })

            .when('/:uv/legal', {
                templateUrl : 'legal.html',
                controller : 'EmptyCtrl'
            })

            .otherwise({
                resolve: {error: ['$q', function($q) {
                    return $q.reject({statusText: "That page does not exist"});
                }]}
            });

        $animateProvider.classNameFilter(/animate/);

        logProvider.setLevel('info');

        // Set up XSRF protection for Tornado.
        // http://tornado.readthedocs.org/en/branch4.0/web.html#tornado.web.RequestHandler.check_xsrf_cookie
        $httpProvider.defaults.xsrfCookieName = '_xsrf';
        $httpProvider.defaults.xsrfHeaderName = 'X-Xsrftoken';

        // Add a delay to all requests - simulates network latency.
        // http://blog.brillskills.com/2013/05/simulating-latency-for-angularjs-http-calls-with-response-interceptors/
//        var handlerFactory = ['$q', '$timeout', function($q, $timeout) {
//            return function(promise) {
//                return promise.then(function(response) {
//                    return $timeout(function() {
//                        return response;
//                    }, 500);
//                }, function(response) {
//                    return $q.reject(response);
//                });
//            };
//        }];
//
//        $httpProvider.responseInterceptors.push(handlerFactory);
}])



/*
 * Install an HTTP interceptor to make error reasons easier to use. All HTTP
 * responses will have the "reason" in the statusText field.
 */
.config(['$httpProvider',
    function($httpProvider) {
        $httpProvider.interceptors.push(['$q', function($q) {
            return {
                response: function(response) {
                    var reason = response.headers('Operation-Details');
                    if (reason)
                        response.statusText = reason;
                    return response;
                },
                responseError: function(rejection) {
                    if (!rejection.headers)
                        return $q.reject(rejection);
                    var reason = rejection.headers('Operation-Details');
                    if (reason)
                        rejection.statusText = reason;
                    return $q.reject(rejection);
                }
            };
        }]);
    }
])


/*
 * Global config for some 3rd party libraries.
 */
.config(function() {
    Dropzone.autoDiscover = false;
})


.run(['$cacheFactory', '$http', function($cacheFactory, $http) {
    $http.defaults.cache = $cacheFactory('lruCache', {capacity: 100});
}])


.factory('Authz', function(AuthzPolicy, currentUser, $cookies) {
    var policyFactory = function(context) {
        var localPolicy = policyFactory.rootPolicy.derive(context);
        return function(ruleName) {
            return localPolicy.check(ruleName);
        };
    };
    policyFactory.rootPolicy = new AuthzPolicy(null, null, null, 'client');

    policyFactory.rootPolicy.context.s = {
        user: currentUser,
        org: currentUser.organisation,
        superuser: !!$cookies.get('superuser'),
    };

    return policyFactory;
})


.config(function(timeAgoSettings) {
    var oneDay = 60 * 60 * 24;
    timeAgoSettings.allowFuture = true;
    timeAgoSettings.fullDateAfterSeconds = oneDay * 3;
})

;
