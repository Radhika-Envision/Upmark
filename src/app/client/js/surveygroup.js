'use strict'

angular.module('upmark.surveygroup', [
    'ngResource', 'upmark.notifications', 'vpac.utils.requests'])


.config(function($routeProvider) {
    $routeProvider
        .when('/:uv/surveygroups', {
            templateUrl : 'surveygroup_list.html',
            controller : 'SurveyGroupListCtrl'
        })
        .when('/:uv/surveygroup/new', {
            templateUrl : 'surveygroup.html',
            controller : 'SurveyGroupCtrl',
            resolve: {
                surveygroup: function() {
                    return null;
                }
            }
        })
        .when('/:uv/surveygroup/:id', {
            templateUrl : 'surveygroup.html',
            controller : 'SurveyGroupCtrl',
            resolve: {
                surveygroup: ['SurveyGroup', '$route',
                        function(SurveyGroup, $route) {
                    return SurveyGroup.get({
                        id: $route.current.params.id
                    }).$promise;
                }]
            }
        })
    ;
})


.factory('SurveyGroup', ['$resource', 'paged', function($resource, paged) {
    return $resource('/surveygroup/:id.json', {id: '@id'}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT', cache: false },
        query: {
            method: 'GET', isArray: true, cache: false,
            interceptor: {response: paged}
        },
        create: { method: 'POST', cache: false },
    });
}])


.controller('SurveyGroupCtrl', function(
        $scope, SurveyGroup, surveygroup, Editor, Authz, $location, $q) {

    $scope.edit = Editor('surveygroup', $scope);
    if (surveygroup) {
        // Editing old
        $scope.surveygroup = surveygroup;
    } else {
        // Creating new
        $scope.surveygroup = new SurveyGroup({});
        $scope.edit.edit();
    }

    $scope.save = function() {
        var async_task_promises = [];
        $scope.$broadcast('prepareFormSubmit', async_task_promises);
        var promise = $q.all(async_task_promises).then(
            function success(async_tasks) {
                return $scope.edit.save();
            },
            function failure(reason) {
                return $q.reject(reason);
            }
        );
    }

    $scope.$on('EditSaved', function(event, model) {
        $location.url('/3/surveygroup/' + model.id);
    });
    $scope.$on('EditDeleted', function(event, model) {
        $location.url('/3/surveygroups');
    });

    $scope.checkRole = Authz({surveygroup: $scope.surveygroup});
})


.controller('SurveyGroupListCtrl', function(
        $scope, Authz, SurveyGroup, Notifications, $q) {

    $scope.surveygroups = null;
    $scope.checkRole = Authz({});

    $scope.search = {
        term: "",
        deleted: false,
        page: 0,
        pageSize: 10
    };
    $scope.$watch('search', function(search) {
        SurveyGroup.query(search).$promise.then(
            function success(surveygroups) {
                $scope.surveygroups = surveygroups;
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
