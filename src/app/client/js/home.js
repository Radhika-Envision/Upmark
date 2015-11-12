'use strict';

angular.module('wsaa.home', ['ngResource'])


.factory('Activity', ['$resource', function($resource) {
    return $resource('/activity.json', {}, {
        get: { method: 'GET', cache: true }
    });
}])


.controller('HomeCtrl', ['$scope', 'Activity', 'Notifications', '$q', 'format',
        function($scope, Activity, Notifications, $q, format) {

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

    $scope.url = function(action) {
        switch (action.obType) {
        case 'organisation':
            return format("/org/{}", action.obIds[0]);
        case 'user':
            return format("/user/{}", action.obIds[0]);
        case 'program':
            return format("/survey/{}", action.obIds[0]);
        case 'survey':
            return format("/hierarchy/{}?survey={}",
                action.obIds[0], action.obIds[1]);
        case 'qnode':
            return format("/qnode/{}?survey={}",
                action.obIds[0], action.obIds[1]);
        case 'measure':
            return format("/measure/{}?survey={}",
                action.obIds[0], action.obIds[1]);
        case 'submission':
            return format("/assessment/{}", action.obIds[0]);
        default:
            return '';
        }
    };

    $scope.icons = function(action) {
        var icons = [];
        for (var i = 0; i < action.verbs.length; i++) {
            var verb = action.verbs[i];
            switch (verb) {
            case 'create':
                icons.push('fa-plus');
                break;
            case 'update':
                icons.push('fa-pencil');
                break;
            case 'state':
                icons.push('fa-chevron-right');
                break;
            case 'delete':
                icons.push('fa-trash-o');
                break;
            case 'relation':
                icons.push('fa-link');
                break;
            case 'reorder_children':
                icons.push('fa-arrows-v');
                break;
            default:
            }
        }
        return icons;
    };

}])

;
