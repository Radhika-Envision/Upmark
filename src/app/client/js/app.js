'use strict';

angular.module('wsaa.aquamark',
               ['ngRoute', 'ngAnimate', 'ui.bootstrap', 'cfp.hotkeys',
                'ui.bootstrap.showErrors', 'validation.match', 'settings',
                'wsaa.survey', 'wsaa.admin', 'vpac.utils', 'vpac.widgets'])


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
            .when('/survey/:survey/:fn/:proc/:subProc/:measure', {
                templateUrl : 'survey-measure.html',
                controller : 'SurveyCtrl',
                resolve: {routeData: chain({
                    measure: ['Measure', '$route', function(Measure, $route) {
                        return Measure.get($route.current.params).$promise;
                    }],
                    schema: ['measure', 'Schema', function(measure, Schema) {
                        return Schema.get({name: measure.responseType}).$promise;
                    }]
                })}
            })
            .when('/', {
                templateUrl : 'start.html',
                controller : 'EmptyCtrl'
            })
            .when('/users', {
                templateUrl : 'user_list.html',
                controller : 'AdminCtrl'
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
                    }],
                    org: ['user', 'Organisation', function(user, Organisation) {
                        if (!user.organisation)
                            return null;
                        return Organisation.get({id: user.organisation}).$promise;
                    }]
                })}
            })
            .when('/org/:id', {
                templateUrl : 'organisation.html',
                controller : 'OrganisationCtrl',
                resolve: {
                    org: ['Organisation', '$route', function(Organisation, $route) {
                        return Organisation.get($route.current.params).$promise;
                    }]
                }
            })
            .when('/legal', {
                templateUrl : 'legal.html',
                controller : 'EmptyCtrl'
            })
            .otherwise({
                redirectTo : '/'
            });

        $animateProvider.classNameFilter(/ng-animate-enabled/);

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


.controller('RootCtrl', ['$scope',
        function($scope) {
}])
.controller('EmptyCtrl', ['$scope',
        function($scope) {
}])
.controller('LoginCtrl', ['$scope',
        function($scope) {
}])
.controller('AdminCtrl', ['$scope', 'User',
        function($scope, User) {
            User.query({}).$promise.then(function(data){
                $scope.users = data;
            })
}])
;
