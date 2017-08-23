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


.controller('SurveyGroupCtrl',
        function($location, $q, $scope, $timeout, $window,
            Authz, Editor, SurveyGroup, surveygroup) {

    var window = angular.element($window);

    $scope.ellipsize = function(surveygroup) {
        /**
         * Truncate string and replace last overflowing word with ellipsis
         * http://stackoverflow.com/a/3880955
        */
        let container = angular.element($('.surveygroup-desc'));
        let content = angular.element($('.desc-content'));
        let containerHeight = container.height()

        // Truncate description if it's very long to avoid a lot of
        // replace operations
        if (surveygroup.description.length > 300) {
            content.text(surveygroup.description.substr(0, 300));
        } else {
            content.text(surveygroup.description);
        };

        while (content.outerHeight() > containerHeight) {
            content.text(function (index, text) {
                return text.replace(/\W*\s(\S)*$/, '...');
            });
        };
    };

    $scope.$watch('surveygroup', function(surveygroup) {
        if (surveygroup && surveygroup.description)
            $timeout(function() { $scope.ellipsize(surveygroup) }, 500)
    })

    $scope.edit = Editor('surveygroup', $scope);
    if (surveygroup) {
        // Editing old
        $scope.surveygroup = surveygroup;
    } else {
        // Creating new
        $scope.surveygroup = new SurveyGroup({});
        $scope.surveygroup.groupLogo = {
            'type': 'image',
            'accept': '.svg',
        };
        $scope.edit.edit();
    }

    $scope.save = function() {
        var async_task_promises = [];
        $scope.$broadcast('prepareFormSubmit', async_task_promises);
        var promise = $q.all(async_task_promises).then(
            function success(async_tasks) {
                $window.location.reload();
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

    window.bind('resize', function() {
        let sg = $scope.surveygroup;
        if (sg && sg.description)
            $scope.ellipsize(sg)
    })
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
