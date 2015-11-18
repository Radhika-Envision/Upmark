'use strict';

angular.module('wsaa.home', ['ngResource', 'wsaa.admin'])


.factory('Activity', ['$resource', function($resource) {
    return $resource('/activity/:id.json', {}, {
        get: { method: 'GET', cache: false },
        save: { method: 'PUT', cache: false },
        create: { method: 'POST', cache: false },
        remove: { method: 'DELETE', cache: false }
    });
}])


.factory('Card', ['$resource', function($resource) {
    return $resource('/card/:id.json', {}, {
        query: { method: 'GET', cache: false, isArray: true }
    });
}])


.factory('homeAuthz', ['Roles', function(Roles) {
    return function(current) {
        return function(functionName) {
            if (!current.$resolved)
                return false;
            switch(functionName) {
                case 'post_message':
                    return Roles.hasPermission(current.user.role, 'org_admin');
                case 'post_to_all':
                    return Roles.hasPermission(current.user.role, 'admin');
                case 'modify_post':
                    return Roles.hasPermission(current.user.role, 'org_admin');
            }
            return false;
        };
    };
}])


.controller('HomeCtrl', ['$scope', 'Activity', 'Notifications', '$q', 'format',
            'Current', 'homeAuthz', 'Card',
        function($scope, Activity, Notifications, $q, format, Current,
            homeAuthz, Card) {

    $scope.activity = null;
    $scope.current = Current;

    $scope.cards = Card.query({});

    $scope.secondsInADay = 24 * 60 * 60;
    $scope.activityParams = {
        period: 7 * $scope.secondsInADay,
        until: Date.now() / 1000
    };
    $scope.goToNow = function() {
        $scope.activityParams.until = Date.now() / 1000;
    };
    $scope.previousActivities = function() {
        $scope.activityParams.until -= $scope.activityParams.period;
    };
    $scope.nextActivities = function() {
        $scope.activityParams.until += $scope.activityParams.period;
    };

    $scope.$watch('activityParams', function(vals) {
        $scope.updateActivities();
    }, true);

    $scope.updateActivities = function() {
        Activity.get($scope.activityParams).$promise.then(
            function success(activity) {
                $scope.activity = activity;
                Notifications.remove('activity');
            },
            function failure(details) {
                Notifications.set('activity', 'error',
                    "Could not get recent activity: " + details.statusText);
                return $q.reject(details);
            }
        );
    };

    $scope.verbs = function(action) {
        var expr = "";
        for (var i = 0; i < action.verbs.length; i++) {
            if (i > 0 && i == action.verbs.length - 1)
                expr += " and ";
            else if (i > 0)
                expr += ", ";

            var verb = action.verbs[i];
            switch (verb) {
            case 'broadcast':
                verb = 'broadcast';
                break;
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

    $scope.cls = function(action) {
        switch (action.obType) {
        case 'organisation':
        case 'user':
            return 'association';
        case 'program':
        case 'survey':
        case 'qnode':
        case 'measure':
            return 'question';
        case 'submission':
        case 'rnode':
        case 'response':
        case 'attachment':
            return 'answer';
        default:
            return '';
        }
    };

    $scope.icons = function(action) {
        var icons = [];
        for (var i = 0; i < action.verbs.length; i++) {
            var verb = action.verbs[i];
            switch (verb) {
            case 'broadcast':
                icons.push('fa-envelope');
                break;
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

    $scope.remove = function(action) {
        Activity.remove({id: action.id}).$promise.then(
            function success() {
                $scope.updateActivities();
                Notifications.set('activity', 'success', "Deleted", 5000);
            },
            function failure(details) {
                Notifications.set('activity', 'error',
                    "Could not delete activity: " + details.statusText);
                return $q.reject(details);
            }
        );
    };

    $scope.toggleSticky = function(action) {
        var updatedAction = angular.copy(action);
        updatedAction.sticky = !action.sticky;

        Activity.save({id: action.id}, updatedAction).$promise.then(
            function success(updatedAction) {
                angular.copy(updatedAction, action);
                Notifications.set('activity', 'success', "Saved", 5000);
            },
            function failure(details) {
                Notifications.set('activity', 'error',
                    "Could not save activity: " + details.statusText);
                return $q.reject(details);
            }
        );
    };

    $scope.checkRole = homeAuthz(Current);

    $scope.showPost = false;
    $scope.togglePost = function() {
        $scope.showPost = !$scope.showPost;
        $scope.resetPost();
    };
    $scope.resetPost = function() {
        $scope.post = {
            to: $scope.checkRole('post_to_all') ? 'all' : 'org',
            sticky: true,
            message: ''
        };
    };

    $scope.postMessage = function() {
        Activity.create($scope.post).$promise.then(
            function success(action) {
                $scope.goToNow();
                $scope.showPost = false;
                $scope.resetPost();
                Notifications.set('activity', 'success', "Posted", 5000);
            },
            function failure(details) {
                Notifications.set('activity', 'error',
                    "Could not post message: " + details.statusText);
                return $q.reject(details);
            }
        );
    };

}])

;
