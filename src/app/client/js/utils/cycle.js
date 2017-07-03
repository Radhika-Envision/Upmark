'use strict';

angular.module('vpac.utils.cycle', [])


.factory('tricycle', [function() {
    return function(value) {
        // null -> false -> true -> null etc.
        if (value == null)
            return false;
        else if (value)
            return null;
        else
            return true;
    };
}])


.directive('deleteCycle', [function() {
    return {
        restrict: 'E',
        templateUrl: 'delete_cycle.html',
        replace: true,
        scope: {
            model: '='
        },
        controller: ['$scope', 'tricycle', function($scope, tricycle) {
            $scope.tricycle = tricycle;
        }]
    };
}])


;
