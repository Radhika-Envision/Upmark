'use strict';

angular.module('lcm',
               ['ngRoute', 'ngAnimate',
                'ui.bootstrap.typeahead', 'leaflet-directive',
                'lcm.services', 'lcm.text', 'lcm.events',
                'lcm.controllers', 'lcm.selectable', 'lcm.visualisation',
                'lcm.constraints', 'lcm.query', 'lcm.credits', 'lcm.sticky'])

.config(['$routeProvider', '$httpProvider', '$parseProvider', '$animateProvider',
         'logProvider',
        function($routeProvider, $httpProvider, $parseProvider, $animateProvider,
                logProvider) {

        $routeProvider
            .when('/layer/:datasetId', {
                templateUrl : 'templates/view.html',
                controller : 'ViewCtrl'
            })
            .when('/query/:queryId', {
                templateUrl : 'templates/query.html',
                controller : 'QueryCtrl'
            })
            .when('/query', {
                templateUrl : 'templates/queries.html',
                controller : 'QueryListCtrl'
            })
            .when('/', {
                templateUrl : 'templates/empty.html',
                controller : 'EmptyCtrl'
            })
            .when('/regions', {
                templateUrl : 'templates/regions.html',
                controller : 'RegionSelectController'
            })
            .when('/legal', {
                templateUrl : 'templates/legal.html',
                controller : 'EmptyCtrl'
            })
            .otherwise({
                redirectTo : '/'
            });

        $animateProvider.classNameFilter(/ng-animate-enabled/);

        logProvider.setLevel('info');

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

.run(['lruCache', '$http', function(lruCache, $http) {
    $http.defaults.cache = lruCache;
}])
;
