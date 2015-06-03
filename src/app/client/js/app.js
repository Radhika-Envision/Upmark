'use strict';

angular.module('wsaa.aquamark',
               ['ngRoute', 'ngAnimate', 'ui.bootstrap', 'cfp.hotkeys',
                'wsaa.survey', 'vpac.utils', 'vpac.widgets'])

.config(['$routeProvider', '$httpProvider', '$parseProvider', '$animateProvider',
         'logProvider',
        function($routeProvider, $httpProvider, $parseProvider, $animateProvider,
                logProvider) {

        $routeProvider
            .when('/survey/:survey/:fn/:proc/:subProc/:measure', {
                templateUrl : 'survey-measure.html',
                controller : 'SurveyCtrl'
            })
            .when('/', {
                templateUrl : 'start.html',
                controller : 'EmptyCtrl'
            })
            .when('/login', {
                templateUrl : 'login.html',
                controller : 'LoginCtrl'
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
