'use strict';

angular.module('wsaa.subscription', ['ngResource', 'wsaa.admin'])


.factory('Subscription', ['$resource', function($resource) {
    return $resource('/subscription/:id.json', {}, {
        get: { method: 'GET', cache: false },
        query: { url: '/subscription/:obType/:obIds.json', method: 'GET',
            cache: false, isArray: true },
        save: { method: 'PUT', cache: false },
        create: { method: 'POST', cache: false },
        remove: { method: 'DELETE', cache: false }
    });
}])


.controller('SubscriptionCtrl', ['$scope', 'Subscription', 'Notifications',
            '$q', 'format', 'Current', 'hotkeys', '$route', 'ActivityTransform',
        function($scope, Subscription, Notifications, $q, format, Current,
            hotkeys, $route, ActivityTransform) {

    var ids = $route.current.params.id;
    if (!angular.isArray(ids))
        ids = [ids];

    $scope.acts = ActivityTransform;
    $scope.subscriptions = null;
    $scope.subscription = null;

    Subscription.query({
        obType: $route.current.params.type,
        obIds: ids
    }).$promise.then(
        function success(subscriptions) {
            $scope.subscriptions = subscriptions;
        },
        function failure(details) {
            Notifications.set('subscription', 'error',
                "Could not get subscriptions: " + details.statusText);
            return $q.reject(details);
        }
    );

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

}])


;
