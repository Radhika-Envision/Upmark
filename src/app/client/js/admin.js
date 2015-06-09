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


.controller('UserCtrl', ['$scope', 'User', 'user', 'roles',
        function($scope, User, user, roles) {

    $scope.user = user;
    $scope.roles = roles;
    $scope.roleDict = {};
    for (var i in roles) {
        var role = roles[i];
        $scope.roleDict[role.id] = role;
    }
}])

;
