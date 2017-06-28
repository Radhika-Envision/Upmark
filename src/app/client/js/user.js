'use strict'

angular.module('upmark.user', [
    'ngResource', 'vpac.utils'])


.factory('User', ['$resource', 'paged', function($resource, paged) {
    return $resource('/user/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT', cache: false },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
        create: { method: 'POST', cache: false },
        impersonate: { method: 'PUT', url: '/login/:id', cache: false }
    });
}])


.controller('UserCtrl', [
        '$scope', 'User', 'routeData', 'Editor', 'Organisation', 'Authz',
        '$window', '$location', 'log', 'Notifications', 'Current', '$q',
        'Password', 'format',
        function($scope, User, routeData, Editor, Organisation, Authz,
                 $window, $location, log, Notifications, Current, $q,
                 Password, format) {

    $scope.edit = Editor('user', $scope);
    if (routeData.user) {
        // Editing old
        $scope.user = routeData.user;
    } else {
        // Creating new
        var org;
        if ($location.search().organisationId) {
            org = {
                id: $location.search().organisationId,
                name: $location.search().orgName
            };
        } else {
            org = Current.user.organisation;
        }
        $scope.user = new User({
            role: 'clerk',
            organisation: org,
            emailInterval: 86400,
        });
        $scope.edit.edit();
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/2/user/' + model.id);
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url(format(
            '/2/org/{}', model.organisation.id));
    });

    $scope.roles = routeData.roles;
    $scope.roleDict = {};
    for (var i in $scope.roles) {
        var role = $scope.roles[i];
        $scope.roleDict[role.id] = role;
    }

    $scope.searchOrg = function(term) {
        return Organisation.query({term: term}).$promise;
    };

    $scope.checkRole = Authz({user: $scope.user});

    $scope.impersonate = function() {
        User.impersonate({id: $scope.user.id}).$promise.then(
            function success() {
                $window.location.reload();
            },
            function error(details) {
                Notifications.set('user', 'error',
                    "Could not impersonate: " + details.statusText);
            }
        );
    };

    $scope.$watch('edit.model.password', function(password) {
        if (!password) {
            $scope.passwordCheck = null;
            return;
        }
        Password.test({password: password}).$promise.then(
            function success(body) {
                $scope.passwordCheck = body;
                Notifications.remove('user');
            },
            function failure(details) {
                $scope.passwordCheck = null;
                Notifications.set('user', 'warning',
                    "Could not check password: " + details.statusText);
            }
        );
    });
}])


.controller('UserListCtrl', ['$scope', 'Authz', 'User', 'Current',
            'Notifications', '$q',
        function($scope, Authz, User, Current, Notifications, $q) {

    $scope.users = null;
    $scope.checkRole = Authz({org: $scope.org});

    $scope.search = {
        term: "",
        organisationId: $scope.org && $scope.org.id,
        deleted: $scope.org && $scope.org.deleted ? null : false,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        User.query(search).$promise.then(
            function success(users) {
                $scope.users = users;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list: " + details.statusText);
                return $q.reject(details);
            }
        );
    }, true);
}])


.directive('userList', [function() {
    return {
        restrict: 'E',
        templateUrl: 'user_list.html',
        scope: {
            org: '='
        },
        controller: 'UserListCtrl',
        link: function(scope, elem, attrs) {
            scope.hideOrg = attrs.hideOrg !== undefined;
        }
    }
}])


;
