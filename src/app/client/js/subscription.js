'use strict';

angular.module('upmark.subscription', [
    'ngResource', 'upmark.admin.settings', 'upmark.user'])


.config(function($routeProvider) {
    $routeProvider
        .when('/:uv/subscription/:type', {
            templateUrl : 'subscription.html',
            controller : 'SubscriptionCtrl'
        })
    ;
})

.factory('Subscription', ['$resource', function($resource) {
    return $resource('/subscription/:id.json', {}, {
        get: { method: 'GET', cache: false },
        query: { url: '/subscription/:obType/:obIds.json', method: 'GET',
            cache: false, isArray: true },
        save: { method: 'PUT', cache: false },
        create: { url: '/subscription/:obType/:obIds.json', method: 'POST',
            cache: false },
        remove: { method: 'DELETE', cache: false }
    });
}])


.controller('SubscriptionCtrl', function(
        $scope, Subscription, Notifications, $q, format,
        hotkeys, $route, ActivityTransform) {

    $scope.obType = $route.current.params.type;
    $scope.ids = $route.current.params.id;
    if (!angular.isArray($scope.ids))
        $scope.ids = [$scope.ids];

    $scope.acts = ActivityTransform;
    $scope.subscriptions = null;
    $scope.subscription = null;
    $scope.objectMissing = false;

    $scope.reload = function() {
        Subscription.query({
            obType: $scope.obType,
            obIds: $scope.ids
        }).$promise.then(
            function success(subscriptions) {
                $scope.subscriptions = subscriptions;
                $scope.objectMissing = false;
            },
            function failure(details) {
                if (details.status == 404) {
                    $scope.objectMissing = true;
                } else {
                    Notifications.set('subscription', 'error',
                        "Could not get subscriptions: " + details.statusText);
                }
                return $q.reject(details);
            }
        );
    };

    $scope.$watch('ids', function(ids) {
        $scope.reload();
    }, true);

    $scope.$watch('subscriptions', function(subscriptions) {
        if (!subscriptions || !subscriptions.length) {
            $scope.subscription = null;
            return;
        }

        var subscribed = false;
        for (var i = 0; i < subscriptions.length; i++) {
            var sub = subscriptions[i];
            if (sub.subscribed !== null)
                subscribed = sub.subscribed;
            sub.effectivelySubscribed = subscribed;
        }

        $scope.subscription = subscriptions[subscriptions.length - 1];
    });

    $scope.remove = function(sub) {
        Subscription.remove(
            {id: sub.id},
            function success(resource, getResponseHeaders) {
                var message = "Deleted";
                if (getResponseHeaders('Operation-Details'))
                    message += ": " + getResponseHeaders('Operation-Details');
                Notifications.set('subscription', 'success', message, 5000);
                $scope.reload();
            },
            function failure(details) {
                Notifications.set('subscription', 'error',
                    "Failed to delete: " + details.statusText);
                return $q.reject(details);
            }
        );
    };

    $scope.toggle = function(sub) {
        var success = function(subscription, getResponseHeaders) {
            var message = "Saved";
            if (getResponseHeaders('Operation-Details'))
                message += ": " + getResponseHeaders('Operation-Details');
            Notifications.set('subscription', 'success', message, 5000);
            $scope.reload();
        };
        var failure = function(details) {
            Notifications.set('subscription', 'error',
                "Failed to save: " + details.statusText);
            return $q.reject(details);
        };

        if (sub.id) {
            Subscription.save(
                {id: sub.id},
                {subscribed: !sub.effectivelySubscribed},
                success,
                failure);
        } else {
            Subscription.create(
                {obType: sub.obType, obIds: sub.obIds},
                {subscribed: !sub.effectivelySubscribed},
                success,
                failure);
        }
    };

})


;
