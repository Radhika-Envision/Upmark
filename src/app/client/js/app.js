'use strict';

angular.module('wsaa.aquamark',
               ['ngRoute', 'ngAnimate', 'ui.bootstrap', 'cfp.hotkeys',
                'ui.bootstrap.showErrors', 'validation.match', 'settings',
                'wsaa.survey', 'wsaa.admin', 'wsaa.surveyQuestions',
                'vpac.utils', 'vpac.widgets'])


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
                redirectTo : 'surveys'
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
                        return Organisation.get($route.current.params).$promise;
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
                resolve: {routeData: chain({})}
            })
            .when('/survey/:survey', {
                templateUrl : 'survey.html',
                controller : 'SurveyCtrl',
                resolve: {routeData: chain({
                    survey: ['Survey', '$route', function(Survey, $route) {
                        return Survey.get({
                            id: $route.current.params.survey
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
                    }],
                    qnodes: ['QuestionNode', 'hierarchy', 'survey',
                            function(QuestionNode, hierarchy, survey) {
                        return QuestionNode.query({
                            hierarchyId: hierarchy.id,
                            surveyId: survey.id
                        }).$promise;
                    }]
                })}
            })

            .when('/qnode/new', {
                templateUrl : 'question_node.html',
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
                templateUrl : 'question_node.html',
                controller : 'QuestionNodeCtrl',
                resolve: {routeData: chain({
                    qnode: ['QuestionNode', '$route',
                            function(QuestionNode, $route) {
                        return QuestionNode.get({
                            id: $route.current.params.qnode,
                            surveyId: $route.current.params.survey
                        }).$promise;
                    }],
                    children: ['QuestionNode', '$route',
                            function(QuestionNode, $route) {
                        return QuestionNode.query({
                            parentId: $route.current.params.qnode,
                            surveyId: $route.current.params.survey
                        }).$promise;
                    }],
                    measures: ['Measure', '$route',
                            function(Measure, $route) {
                        return Measure.query({
                            qnodeId: $route.current.params.qnode,
                            surveyId: $route.current.params.survey
                        }).$promise;
                    }]
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
                    parent: ['QuestionNode', '$route',
                            function(QuestionNode, $route) {
                        if (!$route.current.params.parent)
                            return null;
                        return QuestionNode.get({
                            id: $route.current.params.parent,
                            surveyId: $route.current.params.survey
                        }).$promise;
                    }],
                    measure: ['Measure', '$route', function(Measure, $route) {
                        return Measure.get({
                            id: $route.current.params.measure,
                            surveyId: $route.current.params.survey,
                            hierarchyId: $route.current.params.hierarchy,
                            parentId: $route.current.params.parent
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
        var excludes = versionedResources.exclude.map(function(r) {
            return new RegExp(r);
        });

        $httpProvider.interceptors.push([function() {
            return {
                request: function(config) {
                    var test = function(r) {
                        return r.test(config.url);
                    };
                    if (includes.some(test) && !excludes.some(test)) {
                        var query;
                        if (config.url.indexOf('?') == -1)
                            query = '?v=' + deployId;
                        else
                            query = '&v=' + deployId;
                        config.url += query;
                    }
                    return config;
                }
            }
        }]);
    }
])


.run(['$cacheFactory', '$http', function($cacheFactory, $http) {
    $http.defaults.cache = $cacheFactory('lruCache', {capacity: 100});
}])


.run(['$rootScope', '$window', '$location', 'Notifications', 'log',
        function($rootScope, $window, $location, Notifications, log) {
    $rootScope.$on('$routeChangeError',
            function(event, current, previous, rejection) {
        var error;
        if (rejection && rejection.statusText)
            error = rejection.statusText;
        else
            error = "Object not found";
        log.error("Failed to navigate to {}", $location.url());
        Notifications.set('route', 'error', error, 10000);
        if (previous) {
            $window.history.back();
        } else {
            $location.path("/");
        }
    });
}])


.controller('RootCtrl', ['$scope', 'hotkeys',
        function($scope, hotkeys) {
    $scope.hotkeyHelp = hotkeys.toggleCheatSheet;
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
