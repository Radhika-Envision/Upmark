'use strict'

angular.module('upmark.group', [
    'ngResource', 'upmark.notifications', 'vpac.utils.requests'])


.factory('Group', ['$resource', 'paged', function($resource, paged) {
    return $resource('/group/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT', cache: false },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
        create: { method: 'POST', cache: false },
    });
}])


.controller('GroupCtrl', function(
        $scope, Group, routeData, Editor, Authz, $location) {

    $scope.edit = Editor('group', $scope);
    if (routeData.group) {
        // Editing old
        $scope.group = routeData.group;
    } else {
        // Creating new
        $scope.group = new Group({});
        $scope.edit.edit();
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/2/group/' + model.id);
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url('/2/groups');
    });

    $scope.checkRole = Authz({group: $scope.group});
})


.controller('GroupListCtrl', function(
        $scope, Authz, Group, Notifications, $q) {

    $scope.groups = null;
    $scope.checkRole = Authz({});

    $scope.search = {
        term: "",
        deleted: false,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        Group.query(search).$promise.then(
            function success(groups) {
                $scope.groups = groups;
            },
            function failure(details) {
                Notifications.set('get', 'error',
                    "Could not get list: " + details.statusText);
                return $q.reject(details);
            }
        );
    }, true);
})


;
