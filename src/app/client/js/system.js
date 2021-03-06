'use strict'

angular.module('upmark.system', [
    'ngResource', 'upmark.admin.settings', 'upmark.authz',
    'upmark.notifications', 'upmark.user'])


.config(function($routeProvider) {
    $routeProvider
        .when('/:uv/admin', {
            templateUrl : 'systemconfig.html',
            controller : 'SystemConfigCtrl',
            resolve: {
                systemConfig: ['SystemConfig', function(SystemConfig) {
                    return SystemConfig.get().$promise;
                }]
            }
        })
    ;
})


.factory('SystemConfig', ['$resource', function($resource) {
    return $resource('/systemconfig.json', {}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT', cache: false },
    });
}])


.controller('SystemConfigCtrl',
        function($scope, SystemConfig, Editor, Authz,
            systemConfig, $q, Notifications, $window) {

    $scope.edit = Editor('systemConfig', $scope);
    $scope.systemConfig = systemConfig;
    $scope.state = {
        cacheBust: Date.now(),
        showPreview: false,
    };

    $scope.$watch('systemConfig', function(systemConfig) {
        // Small hack to get Editor utilty to use PUT instead of POST
        if (!systemConfig.id)
            systemConfig.id = 'systemConfig';
    });

    $scope.save = function() {
        var async_task_promises = [];
        $scope.$broadcast('prepareFormSubmit', async_task_promises);
        var promise = $q.all(async_task_promises).then(
            function success(async_tasks) {
                return $scope.edit.save();
            },
            function success(systemconfig) {
                Notifications.remove('systemConfig');
                $window.location.reload();
                $scope.state.cacheBust = Date.now();
            },
            function failure(reason) {
                Notifications.set('systemConfig', 'error', reason);
                $scope.state.cacheBust = Date.now();
                return $q.reject(reason);
            }
        );
    };

    $scope.checkRole = Authz({});
})


;
