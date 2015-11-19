'use strict';

angular.module('wsaa.subscription', ['ngResource', 'wsaa.admin'])


.factory('Subscription', ['$resource', function($resource) {
    return $resource('/subscription/:id.json', {}, {
        get: { method: 'GET', cache: false },
        query: { url: '/subscription/:obType/:obIds.json', method: 'GET',
            cache: false },
        save: { method: 'PUT', cache: false },
        create: { method: 'POST', cache: false },
        remove: { method: 'DELETE', cache: false }
    });
}])


.controller('SubscriptionCtrl', ['$scope', 'Subscription', 'Notifications',
            '$q', 'format', 'Current', 'hotkeys', '$route',
        function($scope, Subscription, Notifications, $q, format, Current,
            hotkeys, $route) {

    var ids = $route.current.params.id;
    if (!angular.isArray(ids))
        ids = [ids];

    $scope.subDetails = {
        obType: $route.current.params.type
    };

    Subscription.query({
        obType: $route.current.params.type,
        obIds: ids
    }).$promise.then(
        function success(subDetails) {
            $scope.subDetails = subDetails;
        },
        function failure(details) {
            Notifications.set('subscription', 'error',
                "Could not get subscriptions: " + details.statusText);
            return $q.reject(details);
        }
    );

}])


;
