'use strict';

angular.module('wsaa.admin', ['ngResource'])


.factory('User', ['$resource', function($resource) {
    return $resource('/user/:id.json', {id: '@id'}, {
        get: { method: 'GET' }
    });
}])


.factory('Roles', ['$resource', function($resource) {
    return $resource('/roles.json', {}, {
        get: { method: 'GET', isArray: true }
    });
}])


.factory('Organisation', ['$resource', function($resource) {
    return $resource('/organisation/:id.json', {id: '@id'}, {
        get: { method: 'GET' }
    });
}])


.controller('UserCtrl', ['$scope', 'User', 'Roles', '$routeParams',
        function($scope, User, Roles, $routeParams) {

    $scope.user = User.get($routeParams);
    $scope.roles = Roles.get();
    $scope.roleDict = {};
    $scope.$watch('roles', function(roles) {
        roles.$promise.then(function(roles) {
            var dict = {};
            for (var i in roles) {
                var role = roles[i];
                dict[role.id] = role;
            }
            $scope.roleDict = dict;
        });
    });
}])

;
