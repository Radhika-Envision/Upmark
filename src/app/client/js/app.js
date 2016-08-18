'use strict';

angular.module('wsaa.aquamark',
               ['ngRoute', 'ngAnimate', 'ui.bootstrap', 'cfp.hotkeys',
                'ui.bootstrap.showErrors', 'validation.match', 'settings',
                'yaru22.angular-timeago', 'angular-select-text',
                'angular-medium-editor', 'msieurtoph.ngCheckboxes',
                'angular-input-stars',
                'wsaa.admin', 'wsaa.home', 'wsaa.subscription',
                'wsaa.response',
                'wsaa.surveyQuestions', 'wsaa.surveyAnswers',
                'vpac.utils', 'vpac.widgets', 'diff-match-patch'])


/**
 * Automatically resolves interdependencies between injected arguments.
 * Returns a function that can be used with $routeProvier.when's resolve
 * parameter.
 */
.provider('chain', function resolveChain() {

    function CyclicException(deps) {
        this.message = "Detected cyclic dependency: " + deps.join(" -> ");
        this.name = 'CyclicException';
    };

    var updateDepth = function(visited, decl, decls, depth) {
        if (decl.depth === undefined || decl.depth < depth)
            decl.depth = depth;
        for (var i = 0; i < decl.length - 1; i ++) {
            var dependency = decl[i];
            if (visited.indexOf(dependency) >= 0)
                throw new CyclicException(visited.concat(dependency));
            if (decls[dependency]) {
                updateDepth(visited.concat(dependency), decls[dependency],
                    decls, depth + 1);
            }
        }
        return null;
    };

    /*
     * Compile a resolution declaration to resolve interdependencies.
     */
    var _chain = function($q, $injector, log, deps) {
        deps = angular.copy(deps);

        var orderedDeps = [];
        for (var name in deps) {
            var dep = deps[name];
            updateDepth([name], dep, deps, 0);
            orderedDeps.push({name: name, dep: dep})
        }
        orderedDeps.sort(function(a, b) {
            return b.dep.depth - a.dep.depth;
        });

        var resolvedDeps = {};
        angular.forEach(orderedDeps, function(value) {
            var name = value.name;
            var dep = value.dep;
            if (angular.isString(dep)) {
                resolvedDeps[name] = $injector.get(dep);
                return;
            }

            var locals = {};
            for (var j = 0; j < dep.length - 1; j++) {
                var dependency = dep[j];
                if (resolvedDeps[dependency])
                    locals[dependency] = $q.when(resolvedDeps[dependency]);
            }

            resolvedDeps[name] = $q.all(locals).then(function(locals) {
                log.debug("Resolving {} with locals {}", name, locals);
                return $injector.invoke(dep, null, locals, name);
            });
        });
        var ret = $q.all(resolvedDeps);
        resolvedDeps = null;
        return ret;
    };

    var chain = function(deps) {
        // Services can't be injected at configure time, so defer injection
        // until run time.
        return ['$q', '$injector', 'log', function($q, $injector, log) {
            return _chain($q, $injector, log, deps);
        }];
    };
    chain.$get = chain;

    return chain;
})


.config(['$routeProvider', '$httpProvider', '$parseProvider', '$animateProvider',
         'logProvider', 'chainProvider',
        function($routeProvider, $httpProvider, $parseProvider, $animateProvider,
                logProvider, chain) {

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

            .when('/:uv/users', {
                templateUrl : 'user_list.html',
                controller : 'UserListCtrl'
            })
            .when('/:uv/user/new', {
                templateUrl : 'user.html',
                controller : 'UserCtrl',
                resolve: {routeData: chain({
                    roles: ['Roles', function(Roles) {
                        return Roles.get().$promise;
                    }]
                })}
            })
            .when('/:uv/user/:id', {
                templateUrl : 'user.html',
                controller : 'UserCtrl',
                resolve: {routeData: chain({
                    roles: ['Roles', function(Roles) {
                        return Roles.get().$promise;
                    }],
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
            .when('/:uv/org/:id/program/add', {
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
                            programId: program.id
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
                    approval: ['$route', function($route) {
                        return $route.current.params.approval || 'draft';
                    }],
                    stats1: ['Statistics', '$route', 'submission1', '$q',
                             'submission2',
                            function(Statistics, $route, submission1, $q,
                                submission2) {
                        return Statistics.get({
                            id: submission1.program.id,
                            parentId: $route.current.params.qnode == '' ?
                                null : $route.current.params.qnode,
                            approval: $route.current.params.approval || 'draft'
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
                    stats2: ['Statistics', '$route', 'submission1',
                             'submission2', 'stats1', '$q',
                            function(Statistics, $route, submission1,
                                     submission2, stats1, $q) {
                        if (!submission2)
                            return null;
                        if (submission1.program.id == submission2.program.id)
                            return stats1;
                        return Statistics.get({
                            id: submission2.program.id,
                            parentId: $route.current.params.qnode == '' ?
                                null : $route.current.params.qnode,
                            approval: $route.current.params.approval || 'draft'
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
            .when('/:uv/adhoc', {
                templateUrl : 'adhoc.html',
                controller : 'AdHocCtrl',
                resolve: {
                    config: ['CustomQueryConfig', function(CustomQueryConfig) {
                        return CustomQueryConfig.get({}).$promise;
                    }],
                    samples: ['SampleQueries', function(SampleQueries) {
                        return SampleQueries.get({}).$promise;
                    }]
                }
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
                    parent: ['QuestionNode', '$route',
                            function(QuestionNode, $route) {
                        if ($route.current.params.submission)
                            return null;
                        if (!$route.current.params.parent)
                            return null;
                        return QuestionNode.get({
                            id: $route.current.params.parent,
                            programId: $route.current.params.program,
                        }).$promise;
                    }],
                    measure: ['Measure', '$route',
                            function(Measure, $route) {
                        return Measure.get({
                            id: $route.current.params.measure,
                            programId: $route.current.params.submission
                                ? null
                                : $route.current.params.program,
                            parentId: $route.current.params.submission
                                ? null
                                : $route.current.params.parent,
                            submissionId: $route.current.params.submission
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
 * Install an HTTP interceptor to add version numbers to the URLs of certain
 * resources. This is to improve the effectiveness of the browser cache, and to
 * give control over when the cache should be invalidated.
 */
.config(['$httpProvider', 'versionedResources', 'deployId',
    function($httpProvider, versionedResources, deployId) {
        if (!deployId)
            return;

        var includes = versionedResources.include.map(function(r) {
            return new RegExp(r);
        });
        var volatile = versionedResources.volatile.map(function(r) {
            return new RegExp(r);
        });
        var excludes = versionedResources.exclude.map(function(r) {
            return new RegExp(r);
        });

        var vseq = 0;

        $httpProvider.interceptors.push([function() {
            return {
                request: function(config) {
                    var test = function(r) {
                        return r.test(config.url);
                    };

                    var cacheBustId = null;
                    if (volatile.some(test) && !excludes.some(test)) {
                        cacheBustId = 'volatile-' + (Date.now() / 1000)
                        cacheBustId += '-' + vseq;
                        vseq = (vseq + 1) % 100;
                    } else if (includes.some(test) && !excludes.some(test)) {
                        cacheBustId = 'static-' + deployId;
                    }

                    if (cacheBustId) {
                        var query;
                        if (config.url.indexOf('?') == -1)
                            query = '?v=' + cacheBustId;
                        else
                            query = '&v=' + cacheBustId;
                        config.url += query;
                    }
                    return config;
                }
            };
        }]);
    }
])


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


.run(['$rootScope', '$window', '$location', 'Notifications', 'log', 'timeAgo',
        '$route', 'checkLogin',
        function($rootScope, $window, $location, Notifications, log, timeAgo,
            $route, checkLogin) {

    // Upgrade route version
    // The route version should be a number in the range 0-z
    $rootScope.$on('$routeChangeStart', function(event, next, current) {
        var path = $location.path();
        var vmatch = /^\/([0-9a-z])\//.exec(path);
        var version = vmatch && vmatch[1] || '0';
        if (version == '0') {
            var oldUrl = $location.url();
            if (path == "")
                path = "/";
            var pElems = path.split('/');
            if (pElems[1] == 'survey') {
                pElems[1] = 'program';
            } else if (pElems[1] == 'surveys') {
                pElems[1] = 'programs';
            } else if (pElems[1] == 'hierarchy') {
                pElems[1] = 'survey';
            } else if (pElems[1] == 'assessment') {
                pElems[1] = 'submission';
            }
            pElems.splice(1, 0, '1');
            $location.path(pElems.join('/'));

            var search = $location.search();
            if (search.survey) {
                $location.search('program', search.survey);
                $location.search('survey', null);
            }
            if (search.hierarchy) {
                $location.search('survey', search.hierarchy);
                $location.search('hierarchy', null);
            }
            if (search.assessment) {
                $location.search('submission', search.assessment);
                $location.search('assessment', null);
            }
            if (search.assessment1) {
                $location.search('submission1', search.assessment1);
                $location.search('assessment1', null);
            }
            if (search.assessment2) {
                $location.search('submission2', search.assessment2);
                $location.search('assessment2', null);
            }
            console.log("Upgraded route:", oldUrl, $location.url())
        }

        if (version != '1')
            $location.replace();
    });

    $rootScope.$on('$routeChangeError',
            function(event, current, previous, rejection) {
        var error;
        if (rejection && rejection.statusText)
            error = rejection.statusText;
        else if (rejection && rejection.message)
            error = rejection.message;
        else if (angular.isString(rejection))
            error = rejection;
        else
            error = "Object not found";
        log.error("Failed to navigate to {}", $location.url());
        Notifications.set('route', 'error', error, 10000);

        checkLogin().then(
            function sessionStillValid() {
                if (previous)
                    $window.history.back();
            },
            function sessionInvalid() {
                Notifications.set('route', 'error',
                    "Your session has expired. Please log in again.");
            }
        );
    });

    $rootScope.$on('$routeChangeSuccess', function(event) {
        $window.ga('send', 'pageview', '/' + $route.current.loadedTemplateUrl);
    });

    var oneDay = 60 * 60 * 24;
    timeAgo.settings.allowFuture = true;
    timeAgo.settings.fullDateAfterSeconds = oneDay * 3;
}])


.controller('RootCtrl', ['$scope', 'hotkeys', '$cookies', 'User',
        'Notifications', '$window', 'aqVersion',
        function($scope, hotkeys, $cookies, User, Notifications, $window,
            aqVersion) {
    $scope.aqVersion = aqVersion;
    $scope.hotkeyHelp = hotkeys.toggleCheatSheet;

    try {
        var superuser = $cookies.get('superuser');
        if (superuser) {
            var pastUsers = decodeURIComponent($cookies.get('past-users'));
            $scope.pastUsers = angular.fromJson(pastUsers);
        } else {
            $scope.pastUsers = null;
        }
    } catch (e) {
        $scope.pastUsers = null;
    }

    $scope.impersonate = function(id) {
        User.impersonate({id: id}).$promise.then(
            function success() {
                $window.location.reload();
            },
            function error(details) {
                Notifications.set('user', 'error',
                    "Could not impersonate: " + details.statusText);
            }
        );
    };

    $scope.trainingDocs = "This is the training site."
        + " You can make changes without affecting the"
        + " main site. Sometimes, information is copied from the"
        + " main site to this one. When that happens, changes you have"
        + " made here will be overwritten.";
}])
.controller('HeaderCtrl', ['$scope', 'confAuthz', 'Current',
        function($scope, confAuthz, Current) {
        $scope.checkRole = confAuthz(Current);
}])
.controller('EmptyCtrl', ['$scope',
        function($scope) {
}])
.controller('LoginCtrl', ['$scope',
        function($scope) {
}])

;
