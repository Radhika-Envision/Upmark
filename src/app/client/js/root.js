'use strict';

angular.module('upmark.root', [])


.config(function($routeProvider, chainProvider) {
    $routeProvider
        .when('/:uv/legal', {
            templateUrl : 'legal.html',
            controller : 'EmptyCtrl'
        })
    ;
})


.controller('RootCtrl', function(
        $scope, hotkeys, $cookies, User, Notifications, $window, deployInfo,
        $route) {
    $scope.deployInfo = deployInfo;
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

    $scope.refresh = function() {
        $route.reload();
    };
})


.controller('HeaderCtrl', function($scope, Authz) {
    $scope.checkRole = Authz({});
})


.controller('EmptyCtrl', ['$scope',
        function($scope) {
}])


.controller('LoginCtrl', ['$scope',
        function($scope) {
}])

;
