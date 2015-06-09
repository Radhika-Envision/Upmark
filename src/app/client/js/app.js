'use strict';

angular.module('wsaa.aquamark',
               ['ngRoute', 'ngAnimate', 'ui.bootstrap', 'cfp.hotkeys',
                'wsaa.survey', 'wsaa.admin', 'vpac.utils', 'vpac.widgets'])

.config(['$routeProvider', '$httpProvider', '$parseProvider', '$animateProvider',
         'logProvider',
        function($routeProvider, $httpProvider, $parseProvider, $animateProvider,
                logProvider) {

        $routeProvider
            .when('/survey/:survey/:fn/:proc/:subProc/:measure', {
                templateUrl : 'survey-measure.html',
                controller : 'SurveyCtrl',
                resolve: {
                    routeData: ['Measure', 'Schema', '$route', '$q',
                            function(Measure, Schema, $route, $q) {
                        var data = {};
                        data.measure = Measure.get($route.current.params);
                        return data.measure.$promise.then(function(measure) {
                            data.schema = Schema.get({name: measure.responseType});
                            return data.schema.$promise;
                        }).then(function(schema) {
                            return data;
                        });
                    }]
                }
            })
            .when('/', {
                templateUrl : 'start.html',
                controller : 'EmptyCtrl'
            })
            .when('/user/:id', {
                templateUrl : 'user.html',
                controller : 'UserCtrl',
                resolve: {
                    user: ['User', '$route', function(User, $route) {
                        return User.get($route.current.params);
                    }],
                    roles: ['Roles', function(Roles) {
                        return Roles.get();
                    }]
                }
            })
            .when('/org/:id', {
                templateUrl : 'organisation.html',
                controller : 'OrganisationCtrl'
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


.run(['$cacheFactory', '$http', function($cacheFactory, $http) {
    $http.defaults.cache = $cacheFactory('lruCache', {capacity: 20});
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
;
