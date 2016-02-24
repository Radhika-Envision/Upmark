'use strict';

angular.module('wsaa.aquamark',
               ['ngRoute', 'ngAnimate', 'ui.bootstrap', 'cfp.hotkeys',
                'ui.bootstrap.showErrors', 'validation.match', 'settings',
                'yaru22.angular-timeago', 'angular-select-text',
                'angular-medium-editor', 'msieurtoph.ngCheckboxes',
                'angular-input-stars',
                'wsaa.survey', 'wsaa.admin', 'wsaa.home', 'wsaa.subscription',
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

            .when('/', {
                templateUrl : 'home.html',
                controller : 'HomeCtrl'
            })

            .when('/admin', {
                templateUrl : 'systemconfig.html',
                controller : 'SystemConfigCtrl',
                resolve: {
                    systemConfig: ['SystemConfig', function(SystemConfig) {
                        return SystemConfig.get().$promise;
                    }]
                }
            })

            .when('/subscription/:type', {
                templateUrl : 'subscription.html',
                controller : 'SubscriptionCtrl'
            })

            .when('/users', {
                templateUrl : 'user_list.html',
                controller : 'UserListCtrl'
            })
            .when('/user/new', {
                templateUrl : 'user.html',
                controller : 'UserCtrl',
                resolve: {routeData: chain({
                    roles: ['Roles', function(Roles) {
                        return Roles.get().$promise;
                    }]
                })}
            })
            .when('/user/:id', {
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

            .when('/orgs', {
                templateUrl : 'organisation_list.html',
                controller : 'OrganisationListCtrl'
            })
            .when('/org/new', {
                templateUrl : 'organisation.html',
                controller : 'OrganisationCtrl',
                resolve: {
                    org: function() {
                        return null;
                    }
                }
            })
            .when('/org/:id', {
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
            .when('/org/:id/survey/add', {
                templateUrl : 'purchased_survey.html',
                controller : 'PurchasedSurveyAddCtrl',
                resolve: {
                    org: ['Organisation', '$route',
                            function(Organisation, $route) {
                        return Organisation.get($route.current.params).$promise;
                    }],
                    survey: ['Survey', '$route',
                            function(Survey, $route) {
                        if (!$route.current.params.survey)
                            return null;
                        return Survey.get({
                            id: $route.current.params.survey
                        }).$promise;
                    }],
                    hierarchies: ['Hierarchy', '$route',
                            function(Hierarchy, $route) {
                        if (!$route.current.params.survey)
                            return null;
                        return Hierarchy.query({
                            surveyId: $route.current.params.survey
                        }).$promise;
                    }]
                }
            })

            .when('/surveys', {
                templateUrl : 'survey_list.html',
                controller : 'SurveyListCtrl'
            })
            .when('/survey/new', {
                templateUrl : 'survey.html',
                controller : 'SurveyCtrl',
                resolve: {routeData: chain({
                    duplicate: ['Survey', '$route', function(Survey, $route) {
                        if (!$route.current.params.duplicate)
                            return null;
                        return Survey.get({
                            id: $route.current.params.duplicate
                        }).$promise;
                    }]
                })}
            })
            .when('/survey/import', {
                templateUrl : 'survey_import.html',
                controller : 'SurveyImportCtrl'
            })
            .when('/survey/:survey', {
                templateUrl : 'survey.html',
                controller : 'SurveyCtrl',
                resolve: {routeData: chain({
                    survey: ['Survey', '$route', function(Survey, $route) {
                        return Survey.get({
                            id: $route.current.params.survey
                        }).$promise;
                    }]
                })}
            })

            .when('/hierarchy/new', {
                templateUrl : 'hierarchy.html',
                controller : 'HierarchyCtrl',
                resolve: {routeData: chain({
                    survey: ['Survey', '$route', function(Survey, $route) {
                        return Survey.get({
                            id: $route.current.params.survey
                        }).$promise;
                    }]
                })}
            })
            .when('/hierarchy/:hierarchy/choice', {
                templateUrl : 'hierarchy_choice.html',
                controller : 'HierarchyChoiceCtrl',
                resolve: {routeData: chain({
                    hierarchy: ['Hierarchy', '$route',
                            function(Hierarchy, $route) {
                        return Hierarchy.get({
                            id: $route.current.params.hierarchy,
                            surveyId: $route.current.params.survey
                        }).$promise;
                    }],
                    survey: ['hierarchy', function(hierarchy) {
                        return hierarchy.survey;
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
            .when('/hierarchy/:hierarchy', {
                templateUrl : 'hierarchy.html',
                controller : 'HierarchyCtrl',
                resolve: {routeData: chain({
                    hierarchy: ['Hierarchy', '$route',
                            function(Hierarchy, $route) {
                        return Hierarchy.get({
                            id: $route.current.params.hierarchy,
                            surveyId: $route.current.params.survey
                        }).$promise;
                    }],
                    survey: ['hierarchy', function(hierarchy) {
                        return hierarchy.survey;
                    }]
                })}
            })

            .when('/assessment/new', {
                templateUrl : 'assessment.html',
                controller : 'AssessmentCtrl',
                resolve: {routeData: chain({
                    survey: ['Survey', '$route', function(Survey, $route) {
                        return Survey.get({
                            id: $route.current.params.survey
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
                    hierarchies: ['Hierarchy', 'survey',
                            function(Hierarchy, survey) {
                        return Hierarchy.query({
                            surveyId: survey.id
                        }).$promise;
                    }],
                    duplicate: ['Assessment', '$route',
                            function(Assessment, $route) {
                        if (!$route.current.params.duplicate)
                            return null;
                        return Assessment.get({
                            id: $route.current.params.duplicate
                        }).$promise;
                    }]
                })}
            })
            .when('/assessment/duplicate', {
                templateUrl : 'assessment_dup.html',
                controller : 'AssessmentDuplicateCtrl',
                resolve: {routeData: chain({
                    survey: ['Survey', '$route', function(Survey, $route) {
                        return Survey.get({
                            id: $route.current.params.survey
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
            .when('/assessment/import', {
                templateUrl : 'assessment_import.html',
                controller : 'AssessmentImportCtrl',
                resolve: {routeData: chain({
                    survey: ['Survey', '$route', function(Survey, $route) {
                        return Survey.get({
                            id: $route.current.params.survey
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
                    hierarchies: ['Hierarchy', 'survey',
                            function(Hierarchy, survey) {
                        return Hierarchy.query({
                            surveyId: survey.id
                        }).$promise;
                    }]
                })}
            })
            .when('/assessment/:assessment', {
                templateUrl : 'assessment.html',
                controller : 'AssessmentCtrl',
                resolve: {routeData: chain({
                    assessment: ['Assessment', '$route',
                            function(Assessment, $route) {
                        return Assessment.get({
                            id: $route.current.params.assessment
                        }).$promise;
                    }],
                    survey: ['assessment', function(assessment) {
                        return assessment.survey;
                    }]
                })}
            })

            .when('/qnode/new', {
                templateUrl : 'qnode.html',
                controller : 'QuestionNodeCtrl',
                resolve: {routeData: chain({
                    hierarchy: ['Hierarchy', '$route',
                            function(Hierarchy, $route) {
                        var hierarchyId = $route.current.params.hierarchy;
                        if (!hierarchyId)
                            return null
                        return Hierarchy.get({
                            id: hierarchyId,
                            surveyId: $route.current.params.survey
                        }).$promise;
                    }],
                    parent: ['QuestionNode', '$route',
                            function(QuestionNode, $route) {
                        var parentId = $route.current.params.parent;
                        if (!parentId)
                            return null;
                        return QuestionNode.get({
                            id: parentId,
                            surveyId: $route.current.params.survey
                        }).$promise;
                    }]
                })}
            })
            .when('/qnode/:qnode', {
                templateUrl : 'qnode.html',
                controller : 'QuestionNodeCtrl',
                resolve: {routeData: chain({
                    assessment: ['Assessment', '$route',
                            function(Assessment, $route) {
                        if (!$route.current.params.assessment)
                            return null;
                        return Assessment.get({
                            id: $route.current.params.assessment
                        }).$promise;
                    }],
                    qnode: ['QuestionNode', '$route', 'assessment',
                            function(QuestionNode, $route, assessment) {
                        return QuestionNode.get({
                            id: $route.current.params.qnode,
                            surveyId: assessment ? assessment.survey.id :
                                $route.current.params.survey,
                        }).$promise;
                    }],
                    measures: ['Measure', '$route', 'assessment',
                            function(Measure, $route, assessment) {
                        return Measure.query({
                            qnodeId: $route.current.params.qnode,
                            surveyId: assessment ? assessment.survey.id :
                                $route.current.params.survey,
                        }).$promise;
                    }]
                })}
            })
            .when('/qnode-link', {
                templateUrl : 'qnode_link.html',
                controller : 'QnodeLinkCtrl',
                resolve: {routeData: chain({
                    hierarchy: ['Hierarchy', '$route',
                            function(Hierarchy, $route) {
                        if (!$route.current.params.hierarchy)
                            return null;
                        return Hierarchy.get({
                            id: $route.current.params.hierarchy,
                            surveyId: $route.current.params.survey
                        }).$promise;
                    }],
                    parent: ['QuestionNode', '$route',
                            function(QuestionNode, $route) {
                        if (!$route.current.params.parent)
                            return null;
                        return QuestionNode.get({
                            id: $route.current.params.parent,
                            surveyId: $route.current.params.survey
                        }).$promise;
                    }],
                    survey: ['Survey', '$route', function(Survey, $route) {
                        return Survey.get({
                            id: $route.current.params.survey
                        }).$promise;
                    }],
                })}
            })
            .when('/measure-link', {
                templateUrl : 'measure_link.html',
                controller : 'MeasureLinkCtrl',
                resolve: {routeData: chain({
                    parent: ['QuestionNode', '$route',
                            function(QuestionNode, $route) {
                        return QuestionNode.get({
                            id: $route.current.params.parent,
                            surveyId: $route.current.params.survey
                        }).$promise;
                    }],
                    survey: ['Survey', '$route', function(Survey, $route) {
                        return Survey.get({
                            id: $route.current.params.survey
                        }).$promise;
                    }],
                })}
            })

            .when('/statistics', {
                templateUrl : 'statistics.html',
                controller : 'StatisticsCtrl',
                resolve: {routeData: chain({
                    assessment1: ['Assessment', '$route',
                            function(Assessment, $route) {
                        return Assessment.get({
                            id: $route.current.params.assessment1
                        }).$promise;
                    }],
                    assessment2: ['Assessment', '$route',
                            function(Assessment, $route) {
                        if (!$route.current.params.assessment2)
                            return null;
                        return Assessment.get({
                            id: $route.current.params.assessment2
                        }).$promise;
                    }],
                    rnodes1: ['ResponseNode', '$route',
                            function(ResponseNode, $route) {
                        var qnodeId = $route.current.params.qnode;
                        return ResponseNode.query({
                            assessmentId: $route.current.params.assessment1,
                            parentId: qnodeId,
                            root: qnodeId ? null : ''
                        }).$promise;
                    }],
                    rnodes2: ['ResponseNode', '$route',
                            function(ResponseNode, $route) {
                        if (!$route.current.params.assessment2)
                            return null;
                        var qnodeId = $route.current.params.qnode;
                        return ResponseNode.query({
                            assessmentId: $route.current.params.assessment2,
                            parentId: qnodeId,
                            root: qnodeId ? null : ''
                        }).$promise;
                    }],
                    approval: ['$route', function($route) {
                        return $route.current.params.approval || 'draft';
                    }],
                    stats1: ['Statistics', '$route', 'assessment1', '$q',
                             'assessment2',
                            function(Statistics, $route, assessment1, $q,
                                assessment2) {
                        return Statistics.get({
                            id: assessment1.survey.id,
                            parentId: $route.current.params.qnode == '' ?
                                null : $route.current.params.qnode,
                            approval: $route.current.params.approval || 'draft'
                        }).$promise.then(function(stats1) {
                            if (!assessment2 && stats1.length == 0) {
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
                    stats2: ['Statistics', '$route', 'assessment1',
                             'assessment2', 'stats1', '$q',
                            function(Statistics, $route, assessment1,
                                     assessment2, stats1, $q) {
                        if (!assessment2)
                            return null;
                        if (assessment1.survey.id == assessment2.survey.id)
                            return stats1;
                        return Statistics.get({
                            id: assessment2.survey.id,
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
                    qnode1: ['QuestionNode', '$route', 'assessment1',
                            function(QuestionNode, $route, assessment1) {
                        if (!$route.current.params.qnode)
                            return null;
                        return QuestionNode.get({
                            surveyId: assessment1.survey.id,
                            id: $route.current.params.qnode == '' ?
                                null : $route.current.params.qnode
                        }).$promise;
                    }],
                    qnode2: ['QuestionNode', '$route', 'assessment1',
                             'assessment2', 'qnode1',
                            function(QuestionNode, $route, assessment1,
                                     assessment2, qnode1) {
                        if (!$route.current.params.qnode)
                            return null;
                        if (!assessment2)
                            return null;
                        if (assessment1.survey.id == assessment2.survey.id)
                            return qnode1;
                        return QuestionNode.get({
                            surveyId: assessment2.survey.id,
                            id: $route.current.params.qnode == '' ?
                                null : $route.current.params.qnode
                        }).$promise;
                    }]
                })}
            })
            .when('/diff/:survey1/:survey2/:hierarchy', {
                templateUrl: 'diff.html',
                controller: 'DiffCtrl',
                reloadOnSearch: false,
                resolve: {routeData: chain({
                    hierarchy1: ['Hierarchy', '$route',
                            function(Hierarchy, $route) {
                        return Hierarchy.get({
                            id: $route.current.params.hierarchy,
                            surveyId: $route.current.params.survey1
                        }).$promise;
                    }],
                    hierarchy2: ['Hierarchy', '$route',
                            function(Hierarchy, $route) {
                        return Hierarchy.get({
                            id: $route.current.params.hierarchy,
                            surveyId: $route.current.params.survey2
                        }).$promise;
                    }]
                })}
            })
            .when('/adhoc', {
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

            .when('/measures', {
                templateUrl : 'measure_list.html',
                controller : 'MeasureListCtrl',
                resolve: {routeData: chain({
                    survey: ['Survey', '$route', function(Survey, $route) {
                        return Survey.get({
                            id: $route.current.params.survey
                        }).$promise;
                    }],
                })}
            })
            .when('/measure/new', {
                templateUrl : 'measure.html',
                controller : 'MeasureCtrl',
                resolve: {routeData: chain({
                    parent: ['QuestionNode', '$route',
                            function(QuestionNode, $route) {
                        if (!$route.current.params.parent)
                            return null;
                        return QuestionNode.get({
                            id: $route.current.params.parent,
                            surveyId: $route.current.params.survey
                        }).$promise;
                    }],
                    survey: ['Survey', '$route', function(Survey, $route) {
                        return Survey.get({
                            id: $route.current.params.survey
                        }).$promise;
                    }],
                })}
            })
            .when('/measure/:measure', {
                templateUrl : 'measure.html',
                controller : 'MeasureCtrl',
                resolve: {routeData: chain({
                    assessment: ['Assessment', '$route',
                            function(Assessment, $route) {
                        if (!$route.current.params.assessment)
                            return null;
                        return Assessment.get({
                            id: $route.current.params.assessment
                        }).$promise;
                    }],
                    parent: ['QuestionNode', '$route',
                            function(QuestionNode, $route) {
                        if ($route.current.params.assessment)
                            return null;
                        if (!$route.current.params.parent)
                            return null;
                        return QuestionNode.get({
                            id: $route.current.params.parent,
                            surveyId: $route.current.params.survey,
                        }).$promise;
                    }],
                    measure: ['Measure', '$route',
                            function(Measure, $route) {
                        return Measure.get({
                            id: $route.current.params.measure,
                            surveyId: $route.current.params.assessment
                                ? null
                                : $route.current.params.survey,
                            parentId: $route.current.params.assessment
                                ? null
                                : $route.current.params.parent,
                            assessmentId: $route.current.params.assessment
                        }).$promise;
                    }]
                })}
            })

            .when('/legal', {
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


.run(['$cacheFactory', '$http', function($cacheFactory, $http) {
    $http.defaults.cache = $cacheFactory('lruCache', {capacity: 100});
}])


.run(['$rootScope', '$window', '$location', 'Notifications', 'log', 'timeAgo',
        '$route', 'checkLogin',
        function($rootScope, $window, $location, Notifications, log, timeAgo,
            $route, checkLogin) {
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
        'Notifications', '$window', 'aqVersion', 'releaseMode',
        function($scope, hotkeys, $cookies, User, Notifications, $window,
            aqVersion, releaseMode) {
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

    $scope.trainingMode = releaseMode.databaseType == 'local';
    $scope.trainingDocs = "This is the AMCV training site."
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
