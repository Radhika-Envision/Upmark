'use strict';

angular.module('upmark.home', [
    'ngResource', 'upmark.admin.settings', 'upmark.authz', 'upmark.notifications',
    'upmark.user'])


.config(function($routeProvider) {
    $routeProvider
        .when('/:uv/', {
            templateUrl : 'home.html',
            controller : 'HomeCtrl'
        })
    ;
})


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


.service('ActivityTransform', ['format', function(format) {
    this.verbs = function(action) {
        if (!action)
            return "";

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
                verb = 'modified';
                break;
            case 'state':
                verb = 'changed the state of';
                break;
            case 'delete':
                verb = 'deleted';
                break;
            case 'undelete':
                verb = 'undeleted';
                break;
            case 'relation':
                verb = '(re)linked';
                break;
            case 'reorder_children':
                verb = 'reordered the children of';
                break;
            case 'report':
                verb = 'generated a report for';
                break;
            default:
                verb = verb;
            }
            expr += verb;
        }
        return expr;
    };

    this.obType = function(action) {
        if (!action)
            return null;

        switch (action.obType || action) {
        case 'custom_query':
            return 'custom query';
        case 'qnode':
            return 'survey category';
        case 'response_type':
            return 'response type';
        case 'rnode':
            return 'submission category';
        default:
            return action.obType || action;
        }
    };

    this.url = function(action) {
        if (!action)
            return null;

        switch (action.obType) {
        case 'custom_query':
            return format("/3/custom/{}", action.obIds[0]);
        case 'organisation':
            return format("/3/org/{}", action.obIds[0]);
        case 'user':
            return format("/3/user/{}", action.obIds[0]);
        case 'program':
            return format("/3/program/{}", action.obIds[0]);
        case 'survey':
            return format("/3/survey/{}?program={}",
                action.obIds[0], action.obIds[1]);
        case 'qnode':
            return format("/3/qnode/{}?program={}",
                action.obIds[0], action.obIds[1]);
        case 'measure':
            return format("/3/measure/{}?program={}",
                action.obIds[0], action.obIds[1]);
        case 'response_type':
            return format("/3/response-type/{}?program={}",
                action.obIds[0], action.obIds[1]);
        case 'submission':
            return format("/3/submission/{}", action.obIds[0]);
        case 'rnode':
            return format("/3/qnode/{}?submission={}",
                action.obIds[0], action.obIds[1]);
        case 'response':
            return format("/3/measure/{}?submission={}",
                action.obIds[0], action.obIds[1]);
        default:
            return '';
        }
    };

    this.cls = function(action) {
        if (!action)
            return null;

        if (action.verbs && action.verbs[0] == 'broadcast')
            return 'broadcast';

        switch (action.obType) {
        case 'organisation':
        case 'user':
            return 'association';
        case 'program':
        case 'survey':
        case 'qnode':
        case 'measure':
        case 'response_type':
            return 'question';
        case 'submission':
        case 'rnode':
        case 'response':
        case 'attachment':
            return 'answer';
        case 'custom_query':
        default:
            return '';
        }
    };

    this.icons = function(action) {
        if (!action)
            return null;

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
            case 'undelete':
                icons.push('fa-trash-o');
                break;
            case 'relation':
                icons.push('fa-link');
                break;
            case 'reorder_children':
                icons.push('fa-arrows-v');
                break;
            case 'report':
                icons.push('fa-file-text-o');
                break;
            default:
            }
        }
        return icons;
    };
}])


.controller('HomeCtrl',
        function($scope, Activity, Notifications, $q, format,
            Authz, Card, hotkeys, ActivityTransform, Enqueue,
            currentUser, SurveyGroup) {

    $scope.acts = ActivityTransform;
    $scope.activity = null;

    $scope.cards = Card.query({});

    $scope.secondsInADay = 24 * 60 * 60;
    $scope.activityParams = {
        period: 7 * $scope.secondsInADay,
        until: null
    };
    $scope.goToNow = function() {
        $scope.activityParams.until = null;
        $scope.updateActivities();
    };
    $scope.previousActivities = function() {
        var until;
        if ($scope.activity.from)
            until = $scope.activity.from;
        else if ($scope.activityParams.until)
            until = $scope.activityParams.until - $scope.activityParams.period;
        else
            until = (Date.now() / 1000) - $scope.activityParams.period;
        $scope.activityParams.until = until;
    };
    $scope.nextActivities = function() {
        var until;
        if ($scope.activity.until)
            until = $scope.activity.until + $scope.activityParams.period;
        else if ($scope.activityParams.until)
            until = $scope.activityParams.until + $scope.activityParams.period;
        else
            until = (Date.now() / 1000) + $scope.activityParams.period;
        $scope.activityParams.until = until;
    };

    $scope.$watch('activityParams', function(vals) {
        $scope.updateActivities();
    }, true);

    $scope.updateActivities = Enqueue(function() {
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
    }, 0, $scope);

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
                    "Could not save: " + details.statusText);
                return $q.reject(details);
            }
        );
    };

    $scope.subscriptionUrl = function(action) {
        var url = '/3/subscription/' + action.obType;
        for (var i = 0; i < action.obIds.length; i++) {
            if (i == 0)
                url += '?';
            else
                url += '&';
            url += 'id=' + action.obIds[i];
        }
        return url;
    };

    $scope.checkRole = Authz({});

    $scope.post = null;
    $scope.newPost = function() {
        $scope.post = new Activity({
            to: $scope.checkRole('post_to_all') ? 'all' : 'org',
            sticky: true,
            message: '',
            surveygroups: currentUser.surveygroups,
        });
    };
    $scope.cancelEdit = function() {
        $scope.post = null;
    };
    $scope.deleteSurveygroup = function(i) {
        $scope.post.surveygroups.splice(i, 1);
    };
    $scope.searchSurveygroup = function(term) {
        return SurveyGroup.query({term: term}).$promise;
    };

    $scope.postMessage = function() {
        $scope.post.$create().then(
            function success(action) {
                $scope.goToNow();
                $scope.post = null;
                Notifications.set('activity', 'success', "Posted", 5000);
            },
            function failure(details) {
                Notifications.set('activity', 'error',
                    "Could not post message: " + details.statusText);
                return $q.reject(details);
            }
        );
    };

    hotkeys.bindTo($scope)
        .add({
            combo: ['n'],
            description: "Next time period",
            callback: function(event, hotkey) {
                $scope.nextActivities();
            }
        })
        .add({
            combo: ['p'],
            description: "Previous time period",
            callback: function(event, hotkey) {
                $scope.previousActivities();
            }
        })
        .add({
            combo: ['r'],
            description: "Reset (go to current time)",
            callback: function(event, hotkey) {
                $scope.goToNow();
            }
        });

})

;
