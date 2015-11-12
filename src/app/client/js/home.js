'use strict';

angular.module('wsaa.home', ['ngResource'])


.factory('Activity', ['$resource', function($resource) {
    return $resource('/activity.json', {}, {
        get: { method: 'GET', cache: true }
    });
}])


.controller('HomeCtrl', ['$scope', 'Activity', 'Notifications', '$q',
        function($scope, Activity, Notifications, $q) {

    $scope.activity = null;

    Activity.get().$promise.then(
        function success(activity) {
            $scope.activity = activity;
        },
        function failure(details) {
            Notifications.set('get', 'error',
                "Could not get recent activity: " + details.statusText);
            return $q.reject(details);
        }
    );

    $scope.verbs = function(action) {
        var expr = "";
        for (var i = 0; i < action.verbs.length; i++) {
            if (i > 0 && i == action.verbs.length - 1)
                expr += " and ";
            else if (i > 0)
                expr += ", ";

            var verb = action.verbs[i];
            switch (verb) {
            case 'create':
                verb = 'created';
                break;
            case 'update':
                verb = 'changed';
                break;
            case 'state':
                verb = 'changed the state of';
                break;
            case 'delete':
                verb = 'deleted';
                break;
            case 'relation':
                verb = '(re)linked';
                break;
            case 'reorder_children':
                verb = 'reordered the children of';
                break;
            default:
                verb = verb;
            }
            expr += verb;
        }
        return expr;
    };

    $scope.obType = function(action) {
        switch (action.obType) {
        case 'qnode':
            return 'category';
        default:
            return action.obType;
        }
    };

}])

;
